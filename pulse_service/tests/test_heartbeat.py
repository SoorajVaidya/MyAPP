"""Lock heartbeat / extension tests.

These pin down the new safety guarantee that long-running stages must not be
silently stomped when the static TTL expires: the heartbeat refreshes the key
in-place, and if it ever fails (because the key was stolen) the signal worker
abandons the message instead of finishing on stale ownership.

We exercise the lock layer through ``InMemoryLockKV``, which faithfully
implements SET NX PX and the token-checked EVAL surface the lock module relies
on. The Heartbeater is real — only its dependency on Redis is faked.
"""
from __future__ import annotations

import threading
import time
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from global_utils import distributed_lock as dlock_module
from global_utils import event_broker as broker_module
from global_utils import redis_client as redis_client_module
from global_utils.distributed_lock import (
    DistributedLock,
    Heartbeater,
    LockLostError,
    lock_with_heartbeat,
)
from pulse_service.models import AnalysisJob
from pulse_service.workers.signal_worker import SignalWorker

from .fakes import InMemoryBroker, InMemoryLockKV, SyncExecutor
from .fixtures import make_user_and_patient


User = get_user_model()


class HeartbeatExtensionTests(SimpleTestCase):
    def setUp(self) -> None:
        self.kv = InMemoryLockKV()

    def test_extend_keeps_lock_alive_past_original_ttl(self) -> None:
        dl = DistributedLock("k", ttl_ms=50, client=self.kv)
        self.assertTrue(dl.acquire())

        # If we never extend, the key expires and a peer can acquire.
        peer = DistributedLock("k", ttl_ms=50, client=self.kv)
        # Drive the heartbeat at ~10ms so multiple beats happen before the
        # static TTL would have expired.
        hb = Heartbeater(dl, interval_ms=10, ttl_ms=50)
        hb.start()
        try:
            # Sleep well past the original TTL — if the heartbeat works, peer
            # must still see the key held.
            time.sleep(0.2)
            self.assertFalse(peer.acquire())
            self.assertFalse(hb.lost_event.is_set())
        finally:
            hb.stop()
            dl.release()

    def test_extend_fails_when_token_no_longer_owns_key(self) -> None:
        dl = DistributedLock("k", ttl_ms=5000, client=self.kv)
        self.assertTrue(dl.acquire())
        # Simulate the lock being stolen: drop and re-acquire under a peer token.
        self.kv._store.pop("k")
        peer = DistributedLock("k", ttl_ms=5000, client=self.kv)
        self.assertTrue(peer.acquire())

        # Now the original holder's extend must report failure (returns False).
        self.assertFalse(dl.extend())

    def test_heartbeater_signals_lost_when_extend_fails(self) -> None:
        dl = DistributedLock("k", ttl_ms=5000, client=self.kv)
        self.assertTrue(dl.acquire())
        # Steal the key.
        self.kv._store.pop("k")
        peer = DistributedLock("k", ttl_ms=5000, client=self.kv)
        peer.acquire()

        hb = Heartbeater(dl, interval_ms=10, ttl_ms=5000)
        hb.start()
        try:
            # First beat happens after ~10ms; give it room.
            self.assertTrue(hb.lost_event.wait(timeout=1.0))
        finally:
            hb.stop()

    def test_lock_with_heartbeat_yields_check(self) -> None:
        # When the lock is stolen mid-block, .check() must raise.
        with lock_with_heartbeat(
            "k", ttl_ms=5000, heartbeat_ms=10, client=self.kv
        ) as held:
            # Simulate theft.
            self.kv._store.pop("k")
            peer = DistributedLock("k", ttl_ms=5000, client=self.kv)
            peer.acquire()
            # Wait for the heartbeat to notice.
            self.assertTrue(held.heartbeat.lost_event.wait(timeout=1.0))
            with self.assertRaises(LockLostError):
                held.check()


class SignalWorkerHeartbeatTests(TestCase):
    """End-to-end: if a signal job's lock is lost during analysis the worker
    does NOT advance the job, does NOT publish downstream, and does NOT ack —
    the broker's pending list keeps the message available for reclaim.
    """

    def setUp(self) -> None:
        self.broker = InMemoryBroker()
        self.kv = InMemoryLockKV()
        broker_module.set_broker_for_tests(self.broker)
        redis_client_module.reset_for_tests(self.kv)

    def tearDown(self) -> None:
        broker_module.set_broker_for_tests(None)
        redis_client_module.reset_for_tests(None)

    def test_lost_lock_aborts_write_and_leaves_pending(self) -> None:
        user, patient = make_user_and_patient(email="hb@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="hb-tok",
            state=AnalysisJob.STATE_RECEIVED,
            signal_object_key="pulse_signals/hb.txt",
        )
        msg_id = self.broker.enqueue(
            settings.PULSE_STREAM_RECEIVED, {"job_id": str(job.job_id)}
        )

        # Inject a fake heartbeat-lock whose .check() raises LockLostError as
        # if the background heartbeat had reported a stolen key. This keeps
        # the test deterministic — no thread-timing.
        class FakeHeld:
            def check(self_inner):
                raise LockLostError("simulated stolen lock")

        from contextlib import contextmanager as _cm

        @_cm
        def fake_lock_with_heartbeat(_key, ttl_ms):
            yield FakeHeld()

        with mock.patch(
            "pulse_service.workers.signal_worker.lock_with_heartbeat",
            fake_lock_with_heartbeat,
        ), mock.patch(
            "pulse_service.workers.signal_worker.fetch_bytes", return_value=b"raw"
        ):
            worker = SignalWorker(
                broker=self.broker,
                pool=SyncExecutor(),
                analyze=lambda _b: {
                    "primary": "Wind", "secondary": "Heat", "tertiary": "Cold",
                    "quaternary": "Dry", "quinary": None, "extras": {},
                },
            )
            for message in self.broker.consume(
                settings.PULSE_STREAM_RECEIVED,
                settings.PULSE_SIGNAL_GROUP,
                "t",
                count=8,
                block_ms=0,
            ):
                worker._handle(message)

        job.refresh_from_db()
        # Lost-lock must abort BEFORE the ANALYSIS_COMPLETE write — state
        # may have advanced to PROCESSING_SIGNAL, but no result/publish.
        self.assertIn(
            job.state,
            (AnalysisJob.STATE_RECEIVED, AnalysisJob.STATE_PROCESSING_SIGNAL),
        )
        self.assertIsNone(job.analysis_result)
        self.assertEqual(
            self.broker.published(settings.PULSE_STREAM_ANALYSIS_COMPLETE), []
        )
        # Message stayed pending so a peer can reclaim it.
        pending = self.broker.pending(
            settings.PULSE_STREAM_RECEIVED, settings.PULSE_SIGNAL_GROUP
        )
        self.assertIn(msg_id, pending)
