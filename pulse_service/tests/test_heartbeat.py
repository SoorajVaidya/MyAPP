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


class ReportWorkerHeartbeatTests(TestCase):
    """Same contract as SignalWorkerHeartbeatTests, but for the report stage.

    WeasyPrint render + B2 upload can outlive a static TTL; if the heartbeat
    reports a lost lock the worker must NOT mark the job COMPLETED and must
    NOT ack — the pending entry needs to survive for reclaim.
    """

    def setUp(self) -> None:
        self.broker = InMemoryBroker()
        self.kv = InMemoryLockKV()
        broker_module.set_broker_for_tests(self.broker)
        redis_client_module.reset_for_tests(self.kv)

    def tearDown(self) -> None:
        broker_module.set_broker_for_tests(None)
        redis_client_module.reset_for_tests(None)

    def test_lost_lock_after_generate_aborts_completion(self) -> None:
        from pulse_service.workers.report_worker import ReportWorker

        user, patient = make_user_and_patient(email="hbr@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="hbr-tok",
            state=AnalysisJob.STATE_ANALYSIS_COMPLETE,
            analysis_result={"primary": "Wind"},
        )
        msg_id = self.broker.enqueue(
            settings.PULSE_STREAM_ANALYSIS_COMPLETE, {"job_id": str(job.job_id)}
        )

        # First check() (pre-generate) passes; second (post-generate, pre-write)
        # raises. This pins the contract that lock-loss after a successful
        # upload must still abort the COMPLETED transition.
        class FlipHeld:
            def __init__(self_inner):
                self_inner.calls = 0

            def check(self_inner):
                self_inner.calls += 1
                if self_inner.calls >= 2:
                    raise LockLostError("simulated post-generate loss")

        from contextlib import contextmanager as _cm

        held = FlipHeld()

        @_cm
        def fake_lock_with_heartbeat(_key, ttl_ms):
            yield held

        generator_calls = []

        def generator(_job, _result):
            generator_calls.append("ran")
            return "reports/hbr.pdf"

        with mock.patch(
            "pulse_service.workers.report_worker.lock_with_heartbeat",
            fake_lock_with_heartbeat,
        ):
            worker = ReportWorker(
                broker=self.broker,
                generator=generator,
                retry_delays=(0.0, 0.0, 0.0),
                sleep=lambda _s: None,
            )
            for message in self.broker.consume(
                settings.PULSE_STREAM_ANALYSIS_COMPLETE,
                settings.PULSE_REPORT_GROUP,
                "t",
                count=8,
                block_ms=0,
            ):
                worker._handle(message)

        job.refresh_from_db()
        # Generator ran (and uploaded), but the COMPLETED write was aborted.
        self.assertEqual(generator_calls, ["ran"])
        self.assertNotEqual(job.state, AnalysisJob.STATE_COMPLETED)
        self.assertIsNone(job.report_object_key)
        # Message must stay pending so a peer can pick it up via reclaim.
        pending = self.broker.pending(
            settings.PULSE_STREAM_ANALYSIS_COMPLETE, settings.PULSE_REPORT_GROUP
        )
        self.assertIn(msg_id, pending)

    def test_lock_loss_before_first_attempt_skips_generator(self) -> None:
        """A pre-generate loss must NOT call the generator at all — the upload
        is the expensive side-effect we're trying to avoid running on stolen
        ownership."""
        from pulse_service.workers.report_worker import ReportWorker

        user, patient = make_user_and_patient(email="hbr2@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="hbr2-tok",
            state=AnalysisJob.STATE_ANALYSIS_COMPLETE,
            analysis_result={"primary": "Wind"},
        )
        self.broker.enqueue(
            settings.PULSE_STREAM_ANALYSIS_COMPLETE, {"job_id": str(job.job_id)}
        )

        class AlwaysLost:
            def check(self_inner):
                raise LockLostError("lost before first attempt")

        from contextlib import contextmanager as _cm

        @_cm
        def fake_lock_with_heartbeat(_key, ttl_ms):
            yield AlwaysLost()

        calls = []

        def generator(_j, _r):
            calls.append("ran")
            return "reports/x.pdf"

        with mock.patch(
            "pulse_service.workers.report_worker.lock_with_heartbeat",
            fake_lock_with_heartbeat,
        ):
            worker = ReportWorker(
                broker=self.broker, generator=generator,
                retry_delays=(0.0,), sleep=lambda _s: None,
            )
            for message in self.broker.consume(
                settings.PULSE_STREAM_ANALYSIS_COMPLETE,
                settings.PULSE_REPORT_GROUP,
                "t",
                count=8,
                block_ms=0,
            ):
                worker._handle(message)

        self.assertEqual(calls, [])  # generator never called
        job.refresh_from_db()
        self.assertNotEqual(job.state, AnalysisJob.STATE_COMPLETED)
