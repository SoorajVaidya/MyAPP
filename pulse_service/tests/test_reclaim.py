"""Pending-message reclaim tests.

When a consumer SIGKILLs mid-process, its message stays in the consumer
group's pending list. The worker loop's reclaim pass picks those up and
re-dispatches them through the same handler — so a crashed signal worker
doesn't leave a job wedged in PROCESSING_SIGNAL forever.

We exercise reclaim via ``InMemoryBroker``: its ``reclaim_stale`` returns every
pending message on the (stream, group) the loop calls with. That matches how
``XAUTOCLAIM`` behaves once ``min_idle_time`` is satisfied.
"""
from __future__ import annotations

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from global_utils import event_broker as broker_module
from global_utils import redis_client as redis_client_module
from pulse_service.models import AnalysisJob
from pulse_service.workers.base import WorkerLoop
from pulse_service.workers.signal_worker import SignalWorker

from .fakes import InMemoryBroker, InMemoryLockKV, SyncExecutor
from .test_async_pipeline import _make_user_and_patient


User = get_user_model()


class ReclaimDispatchTests(TestCase):
    def setUp(self) -> None:
        self.broker = InMemoryBroker()
        self.kv = InMemoryLockKV()
        broker_module.set_broker_for_tests(self.broker)
        redis_client_module.reset_for_tests(self.kv)

    def tearDown(self) -> None:
        broker_module.set_broker_for_tests(None)
        redis_client_module.reset_for_tests(None)

    def test_reclaimed_message_is_handled_by_loop(self) -> None:
        """A pending message — consumed but never acked — should be picked up
        by the next reclaim pass and re-dispatched to the handler."""
        # Publish, consume (so it goes pending), but never ack.
        msg_id = self.broker.enqueue("s", {"job_id": "stuck"})
        consumed = self.broker.consume("s", "g", "dead-consumer", count=1, block_ms=0)
        self.assertEqual(len(consumed), 1)
        self.assertIn(msg_id, self.broker.pending("s", "g"))

        seen = []

        def handler(msg):
            seen.append(msg.message_id)

        loop = WorkerLoop(
            stream="s",
            group="g",
            handler=handler,
            broker=self.broker,
            consumer_name="healthy-consumer",
            reclaim_min_idle_ms=0,  # always reclaim
            reclaim_every_ms=1,     # every iteration
        )
        # Drive a single reclaim pass.
        loop._maybe_reclaim()
        self.assertEqual(seen, [msg_id])

    def test_reclaim_drives_signal_worker_to_completion(self) -> None:
        """Reclaim should redeliver to SignalWorker._handle, which then runs
        the algo, advances state, and publishes downstream — even though the
        original consumer is gone."""
        user, patient = _make_user_and_patient(email="rc@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="rc-tok",
            state=AnalysisJob.STATE_RECEIVED,
            signal_object_key="pulse_signals/rc.txt",
        )
        msg_id = self.broker.enqueue(
            settings.PULSE_STREAM_RECEIVED, {"job_id": str(job.job_id)}
        )
        # Simulate the original (now-dead) consumer claiming and dying.
        self.broker.consume(
            settings.PULSE_STREAM_RECEIVED,
            settings.PULSE_SIGNAL_GROUP,
            "dead-consumer",
            count=1,
            block_ms=0,
        )
        self.assertIn(
            msg_id, self.broker.pending(
                settings.PULSE_STREAM_RECEIVED, settings.PULSE_SIGNAL_GROUP
            )
        )

        fake_result = {
            "primary": "Wind", "secondary": "Heat", "tertiary": "Cold",
            "quaternary": "Dry", "quinary": None, "extras": {},
        }
        worker = SignalWorker(
            broker=self.broker,
            pool=SyncExecutor(),
            analyze=lambda _bytes: fake_result,
        )
        worker.loop.reclaim_min_idle_ms = 0
        worker.loop.reclaim_every_ms = 1

        with mock.patch(
            "pulse_service.workers.signal_worker.fetch_bytes", return_value=b"raw"
        ):
            worker.loop._maybe_reclaim()

        job.refresh_from_db()
        self.assertEqual(job.state, AnalysisJob.STATE_ANALYSIS_COMPLETE)
        downstream = self.broker.published(settings.PULSE_STREAM_ANALYSIS_COMPLETE)
        self.assertEqual(len(downstream), 1)
        # Reclaim+handler should have acked the original pending message.
        self.assertNotIn(
            msg_id, self.broker.pending(
                settings.PULSE_STREAM_RECEIVED, settings.PULSE_SIGNAL_GROUP
            )
        )

    def test_reclaim_for_already_completed_job_is_idempotent(self) -> None:
        """If the original worker actually completed the work before crashing
        (the ack just never landed), the reclaim handler must NOT re-run the
        algo or republish — it should ack the pending message and move on."""
        user, patient = _make_user_and_patient(email="rc2@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="rc2-tok",
            state=AnalysisJob.STATE_ANALYSIS_COMPLETE,  # already done
            signal_object_key="pulse_signals/rc2.txt",
            analysis_result={"primary": "Wind"},
        )
        msg_id = self.broker.enqueue(
            settings.PULSE_STREAM_RECEIVED, {"job_id": str(job.job_id)}
        )
        self.broker.consume(
            settings.PULSE_STREAM_RECEIVED,
            settings.PULSE_SIGNAL_GROUP,
            "dead-consumer",
            count=1,
            block_ms=0,
        )

        calls = []
        worker = SignalWorker(
            broker=self.broker,
            pool=SyncExecutor(),
            analyze=lambda _b: calls.append("ran") or {},
        )
        worker.loop.reclaim_min_idle_ms = 0
        worker.loop.reclaim_every_ms = 1
        worker.loop._maybe_reclaim()

        self.assertEqual(calls, [])
        self.assertEqual(
            self.broker.published(settings.PULSE_STREAM_ANALYSIS_COMPLETE), []
        )
        self.assertNotIn(
            msg_id, self.broker.pending(
                settings.PULSE_STREAM_RECEIVED, settings.PULSE_SIGNAL_GROUP
            )
        )
