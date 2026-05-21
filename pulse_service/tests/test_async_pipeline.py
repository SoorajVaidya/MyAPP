"""End-to-end exercises of the async pipeline using in-process fakes.

Coverage:
- Idempotency: duplicate pulse.received for an already-advanced job is acked, not re-run.
- Retry: ReportWorker retries a flaky generator and succeeds inside the budget.
- DLQ: ReportWorker exhausts retries on a permanently-failing generator,
       transitions the job to FAILED, and publishes to the DLQ stream.
- State machine: illegal transitions are rejected at the model boundary.
"""
from __future__ import annotations

from datetime import date
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from global_utils import distributed_lock as dlock_module
from global_utils import event_broker as broker_module
from global_utils import redis_client as redis_client_module
from patients.models import PatientsModel
from pulse_service.models import AnalysisJob
from pulse_service.workers.report_worker import ReportWorker
from pulse_service.workers.signal_worker import SignalWorker

from .fakes import InMemoryBroker, InMemoryLockKV, SyncExecutor


User = get_user_model()


def _make_user_and_patient(email: str = "t@example.com") -> tuple:
    # User.phone_number is max_length=15; trim the email-derived value to fit.
    user = User.objects.create(email=email, phone_number=email.replace("@", "_")[:15])
    patient = PatientsModel.objects.create(
        user_profile=user,
        first_name="Test",
        last_name="Patient",
        gender="M",
        dob=date(1990, 1, 1),
        phone_number="9999999999",
        country="X",
        state="Y",
        city="Z",
        email=email + ".pat",
    )
    return user, patient


class AsyncPipelineTestBase(TestCase):
    def setUp(self) -> None:
        self.broker = InMemoryBroker()
        self.kv = InMemoryLockKV()
        broker_module.set_broker_for_tests(self.broker)
        redis_client_module.reset_for_tests(self.kv)

    def tearDown(self) -> None:
        broker_module.set_broker_for_tests(None)
        redis_client_module.reset_for_tests(None)


class SignalWorkerIdempotencyTests(AsyncPipelineTestBase):
    def test_duplicate_event_for_completed_job_is_skipped(self) -> None:
        user, patient = _make_user_and_patient()
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="tok-1",
            state=AnalysisJob.STATE_ANALYSIS_COMPLETE,
            signal_object_key="pulse_signals/abc.txt",
        )

        msg_id = self.broker.enqueue(
            settings.PULSE_STREAM_RECEIVED, {"job_id": str(job.job_id)}
        )

        calls = []
        worker = SignalWorker(
            broker=self.broker,
            pool=SyncExecutor(),
            analyze=lambda _bytes: calls.append("ran") or {"primary": "should_not_run"},
        )
        # Drive one consume + handle cycle manually.
        for message in self.broker.consume(
            settings.PULSE_STREAM_RECEIVED,
            settings.PULSE_SIGNAL_GROUP,
            "test-consumer",
            count=8,
            block_ms=0,
        ):
            worker._handle(message)

        job.refresh_from_db()
        self.assertEqual(job.state, AnalysisJob.STATE_ANALYSIS_COMPLETE)
        self.assertEqual(calls, [])  # algo never invoked for advanced jobs
        self.assertEqual(
            self.broker.published(settings.PULSE_STREAM_ANALYSIS_COMPLETE),
            [],  # no spurious downstream re-fanout
        )

    def test_received_event_advances_to_analysis_complete(self) -> None:
        user, patient = _make_user_and_patient(email="ok@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="tok-2",
            state=AnalysisJob.STATE_RECEIVED,
            signal_object_key="pulse_signals/ok.txt",
        )
        self.broker.enqueue(
            settings.PULSE_STREAM_RECEIVED, {"job_id": str(job.job_id)}
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
        with mock.patch("pulse_service.workers.signal_worker.fetch_bytes", return_value=b"raw"):
            for message in self.broker.consume(
                settings.PULSE_STREAM_RECEIVED,
                settings.PULSE_SIGNAL_GROUP,
                "t",
                count=8,
                block_ms=0,
            ):
                worker._handle(message)

        job.refresh_from_db()
        self.assertEqual(job.state, AnalysisJob.STATE_ANALYSIS_COMPLETE)
        self.assertEqual(job.analysis_result, fake_result)
        downstream = self.broker.published(settings.PULSE_STREAM_ANALYSIS_COMPLETE)
        self.assertEqual(len(downstream), 1)
        self.assertEqual(downstream[0]["job_id"], str(job.job_id))


class ReportWorkerRetryTests(AsyncPipelineTestBase):
    def _make_job(self) -> AnalysisJob:
        user, patient = _make_user_and_patient(email="r@example.com")
        return AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="tok-r",
            state=AnalysisJob.STATE_ANALYSIS_COMPLETE,
            analysis_result={"primary": "Wind"},
        )

    def _drive(self, worker: ReportWorker) -> None:
        for message in self.broker.consume(
            settings.PULSE_STREAM_ANALYSIS_COMPLETE,
            settings.PULSE_REPORT_GROUP,
            "t",
            count=8,
            block_ms=0,
        ):
            worker._handle(message)

    def test_succeeds_within_retry_budget(self) -> None:
        job = self._make_job()
        self.broker.enqueue(
            settings.PULSE_STREAM_ANALYSIS_COMPLETE, {"job_id": str(job.job_id)}
        )

        attempts = {"n": 0}

        def flaky(_job, _result) -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("transient downstream blip")
            return "reports/test.pdf"

        worker = ReportWorker(
            broker=self.broker,
            generator=flaky,
            retry_delays=(0.0, 0.0, 0.0),
            sleep=lambda _s: None,
        )
        self._drive(worker)

        job.refresh_from_db()
        self.assertEqual(job.state, AnalysisJob.STATE_COMPLETED)
        self.assertEqual(job.report_object_key, "reports/test.pdf")
        self.assertEqual(attempts["n"], 3)
        # DLQ remains empty on the happy path.
        self.assertEqual(self.broker.published(settings.PULSE_STREAM_DLQ), [])

    def test_exhausts_retries_then_dlq_and_failed(self) -> None:
        job = self._make_job()
        self.broker.enqueue(
            settings.PULSE_STREAM_ANALYSIS_COMPLETE, {"job_id": str(job.job_id)}
        )

        attempts = {"n": 0}

        def always_fails(_job, _result):
            attempts["n"] += 1
            raise RuntimeError("downstream is on fire")

        worker = ReportWorker(
            broker=self.broker,
            generator=always_fails,
            retry_delays=(0.0, 0.0, 0.0),
            sleep=lambda _s: None,
        )
        self._drive(worker)

        job.refresh_from_db()
        self.assertEqual(job.state, AnalysisJob.STATE_FAILED)
        self.assertEqual(attempts["n"], 4)  # initial + 3 retries
        self.assertEqual(job.error_code, "RuntimeError")
        self.assertIn("downstream is on fire", job.error_message or "")

        dlq = self.broker.published(settings.PULSE_STREAM_DLQ)
        self.assertEqual(len(dlq), 1)
        self.assertEqual(dlq[0]["stage"], "report")
        self.assertEqual(dlq[0]["job_id"], str(job.job_id))


class StateMachineTests(TestCase):
    def test_illegal_transitions_rejected(self) -> None:
        user, patient = _make_user_and_patient(email="sm@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="tok-sm",
            state=AnalysisJob.STATE_RECEIVED,
        )
        with self.assertRaises(AnalysisJob.IllegalTransition):
            job.transition_to(AnalysisJob.STATE_COMPLETED)
        with self.assertRaises(AnalysisJob.IllegalTransition):
            job.transition_to(AnalysisJob.STATE_REPORT_GENERATING)

    def test_failed_is_terminal(self) -> None:
        user, patient = _make_user_and_patient(email="sm2@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="tok-sm2",
            state=AnalysisJob.STATE_FAILED,
        )
        with self.assertRaises(AnalysisJob.IllegalTransition):
            job.transition_to(AnalysisJob.STATE_PROCESSING_SIGNAL)
