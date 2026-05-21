"""Tests for the async report adapter (dynamic_report_service.async_adapter).

These exercise the seam between the async pulse pipeline and the legacy report
generator without standing up WeasyPrint, Redis, or seeded reference data:
`render_pattern_pdf_bytes` and `fetch_bytes` are patched so the heavy render and
B2 fetch never run. Coverage:

- Field mapping: nested-`extras` analysis result -> DiagnosisReportHistory fields,
  and the `parameters` handed to the renderer.
- Idempotency: a second build for the same job reuses the same PulseData +
  DiagnosisReportHistory rows (the report worker retries call this repeatedly).
- Flat-input tolerance: an already-flattened result maps the same way.
- Failure propagation: a renderer ValueError surfaces, and the production
  ReportGenerator wraps it as ReportError.
- Real-adapter retry -> DLQ: ReportWorker driving the real generator ends in
  FAILED with one DLQ message when the renderer keeps failing.
"""
from __future__ import annotations

import hashlib
from datetime import date
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from global_utils import event_broker as broker_module
from global_utils import redis_client as redis_client_module
from patients.models import PatientsModel
from pulse_service.models import AnalysisJob, PulseData
from report_service.models import DiagnosisReportHistory

from pulse_service.tests.fakes import InMemoryBroker, InMemoryLockKV


User = get_user_model()

ADAPTER = "dynamic_report_service.async_adapter"
RENDER = "dynamic_report_service.all_reports.render_pattern_pdf_bytes"
FETCH = "bucket_extentions.s3.fetch_bytes"

NESTED_RESULT = {
    "primary": "Wind",
    "secondary": "Heat",
    "tertiary": "Cold",
    "quaternary": "Dry",
    "quinary": None,
    "extras": {
        "heart_rate": 72.0,
        "heart_yin": 41.5,
        "carbohydrate": "40",
        "protein": "30",
        "fat": "30",
        "wind_yin": "10",
        "wind_yang": "20",
        "heat_yin": "11",
        "heat_yang": "21",
        "humid_yin": "12",
        "humid_yang": "22",
        "dry_yin": "13",
        "dry_yang": "23",
        "cold_yin": "14",
        "cold_yang": "24",
        "vata": "33",
        "pitta": "33",
        "kapha": "34",
    },
}


def _make_user_and_patient(email: str = "adapter@example.com") -> tuple:
    # User.phone_number is max_length=15 and unique; hash to a 14-char prefix
    # so the same email always maps to the same phone and distinct emails do
    # not collide after truncation.
    phone = hashlib.md5(email.encode()).hexdigest()[:14]
    user = User.objects.create(email=email, phone_number=phone)
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


class BuildReportPdfTests(TestCase):
    def setUp(self) -> None:
        self.user, self.patient = _make_user_and_patient()
        self.job = AnalysisJob.objects.create(
            patient=self.patient,
            user=self.user,
            idempotency_token="adapter-tok",
            state=AnalysisJob.STATE_REPORT_GENERATING,
            signal_object_key="pulse_signals/abc.txt",
            analysis_result=NESTED_RESULT,
        )

    def _build(self, result):
        from dynamic_report_service.async_adapter import build_report_pdf

        with mock.patch(RENDER, return_value=b"%PDF-1.4 fake") as render, mock.patch(
            FETCH, return_value=b"1,2,3,4"
        ):
            out = build_report_pdf(self.job, result)
        return out, render

    def test_maps_nested_extras_to_report_history(self) -> None:
        out, render = self._build(NESTED_RESULT)

        self.assertEqual(out, b"%PDF-1.4 fake")
        self.assertEqual(PulseData.objects.count(), 1)
        self.assertEqual(DiagnosisReportHistory.objects.count(), 1)

        rh = DiagnosisReportHistory.objects.get()
        self.assertEqual(rh.user_id, self.user)
        self.assertEqual(rh.patient_id, self.patient)
        self.assertEqual(rh.primary, "Wind")
        self.assertEqual(rh.secondary, "Heat")
        self.assertEqual(rh.vata, "33")
        self.assertEqual(rh.kapha, "34")
        self.assertEqual(rh.wind_yin, "10")
        self.assertEqual(rh.heart_rate, 72.0)
        self.assertEqual(rh.heart_yin, 41.5)
        self.assertIsNone(rh.quinary)

        # PulseData carries the fetched signal text for the optional plot.
        pulse = PulseData.objects.get()
        self.assertEqual(pulse.signal_data, "1,2,3,4")
        self.assertEqual(pulse.pulse_uri, "pulse_signals/abc.txt")

        # Renderer receives (report_history, parameters) positionally + name kwargs.
        kwargs = render.call_args.kwargs
        report_history_arg = render.call_args.args[0]
        parameters_arg = render.call_args.args[1]
        self.assertEqual(report_history_arg.pk, rh.pk)
        self.assertEqual(parameters_arg["primary"], "Wind")
        self.assertEqual(parameters_arg["secondary"], "Heat")
        self.assertEqual(parameters_arg["report_type_override"], "default")
        self.assertEqual(kwargs["patient_name"], "Test Patient")
        self.assertEqual(kwargs["patient_number"], "9999999999")

    def test_idempotent_across_repeated_builds(self) -> None:
        out1, _ = self._build(NESTED_RESULT)
        out2, _ = self._build(NESTED_RESULT)

        self.assertEqual(out1, b"%PDF-1.4 fake")
        self.assertEqual(out2, b"%PDF-1.4 fake")
        # Retries must not duplicate rows.
        self.assertEqual(PulseData.objects.count(), 1)
        self.assertEqual(DiagnosisReportHistory.objects.count(), 1)

    def test_accepts_already_flat_result(self) -> None:
        flat = {
            "primary": "Cold",
            "secondary": "Dry",
            "tertiary": "Wind",
            "quaternary": "Heat",
            "quinary": "Humid",
            "vata": "50",
            "pitta": "25",
            "kapha": "25",
            "heart_rate": "65",
        }
        out, render = self._build(flat)

        self.assertEqual(out, b"%PDF-1.4 fake")
        rh = DiagnosisReportHistory.objects.get()
        self.assertEqual(rh.primary, "Cold")
        self.assertEqual(rh.quinary, "Humid")
        self.assertEqual(rh.vata, "50")
        self.assertEqual(rh.heart_rate, 65.0)

    def test_renderer_failure_propagates(self) -> None:
        from dynamic_report_service.async_adapter import build_report_pdf

        with mock.patch(RENDER, side_effect=ValueError("no matching pattern")), mock.patch(
            FETCH, return_value=b"1,2,3"
        ):
            with self.assertRaises(ValueError):
                build_report_pdf(self.job, NESTED_RESULT)

    def test_missing_signal_key_does_not_block(self) -> None:
        self.job.signal_object_key = None
        self.job.save(update_fields=["signal_object_key"])

        from dynamic_report_service.async_adapter import build_report_pdf

        with mock.patch(RENDER, return_value=b"%PDF") as render, mock.patch(
            FETCH, side_effect=AssertionError("fetch_bytes must not be called when key is None")
        ):
            out = build_report_pdf(self.job, NESTED_RESULT)

        self.assertEqual(out, b"%PDF")
        pulse = PulseData.objects.get()
        self.assertEqual(pulse.pulse_uri, f"pulse_signals/{self.job.job_id}.txt")
        self.assertEqual(pulse.signal_data, "")
        render.assert_called_once()


class ReportGeneratorWrappingTests(TestCase):
    """The production ReportGenerator must surface adapter failures as ReportError."""

    def setUp(self) -> None:
        self.user, self.patient = _make_user_and_patient(email="gen@example.com")
        self.job = AnalysisJob.objects.create(
            patient=self.patient,
            user=self.user,
            idempotency_token="gen-tok",
            state=AnalysisJob.STATE_REPORT_GENERATING,
            signal_object_key="pulse_signals/gen.txt",
            analysis_result=NESTED_RESULT,
        )

    def test_adapter_exception_becomes_report_error(self) -> None:
        from pulse_service.workers.report_client import _DjangoReportGenerator, ReportError

        generator = _DjangoReportGenerator()
        with mock.patch(RENDER, side_effect=ValueError("boom")), mock.patch(
            FETCH, return_value=b"1,2"
        ), mock.patch("bucket_extentions.s3.upload_bytes_with_acl") as upload:
            with self.assertRaises(ReportError):
                generator(self.job, NESTED_RESULT)
        upload.assert_not_called()

    def test_happy_path_uploads_private_and_returns_key(self) -> None:
        from pulse_service.workers.report_client import _DjangoReportGenerator

        generator = _DjangoReportGenerator()
        with mock.patch(RENDER, return_value=b"%PDF-1.4 ok"), mock.patch(
            FETCH, return_value=b"1,2"
        ), mock.patch("bucket_extentions.s3.upload_bytes_with_acl") as upload:
            key = generator(self.job, NESTED_RESULT)

        self.assertEqual(key, f"reports/{self.job.job_id}.pdf")
        upload.assert_called_once()
        _args, kwargs = upload.call_args
        self.assertTrue(kwargs.get("private"))
        self.assertEqual(kwargs.get("content_type"), "application/pdf")


class RealAdapterRetryDLQTests(TestCase):
    """ReportWorker + real generator: a persistently failing render ends in DLQ/FAILED."""

    def setUp(self) -> None:
        self.broker = InMemoryBroker()
        self.kv = InMemoryLockKV()
        broker_module.set_broker_for_tests(self.broker)
        redis_client_module.reset_for_tests(self.kv)

        self.user, self.patient = _make_user_and_patient(email="dlq@example.com")
        self.job = AnalysisJob.objects.create(
            patient=self.patient,
            user=self.user,
            idempotency_token="dlq-tok",
            state=AnalysisJob.STATE_ANALYSIS_COMPLETE,
            signal_object_key="pulse_signals/dlq.txt",
            analysis_result=NESTED_RESULT,
        )

    def tearDown(self) -> None:
        broker_module.set_broker_for_tests(None)
        redis_client_module.reset_for_tests(None)

    def test_persistent_render_failure_routes_to_dlq(self) -> None:
        from pulse_service.workers.report_client import _DjangoReportGenerator
        from pulse_service.workers.report_worker import ReportWorker

        self.broker.enqueue(
            settings.PULSE_STREAM_ANALYSIS_COMPLETE, {"job_id": str(self.job.job_id)}
        )

        worker = ReportWorker(
            broker=self.broker,
            generator=_DjangoReportGenerator(),
            retry_delays=(0.0, 0.0, 0.0),
            sleep=lambda _s: None,
        )

        with mock.patch(RENDER, side_effect=ValueError("no matching pattern")), mock.patch(
            FETCH, return_value=b"1,2,3"
        ):
            for message in self.broker.consume(
                settings.PULSE_STREAM_ANALYSIS_COMPLETE,
                settings.PULSE_REPORT_GROUP,
                "t",
                count=8,
                block_ms=0,
            ):
                worker._handle(message)

        self.job.refresh_from_db()
        self.assertEqual(self.job.state, AnalysisJob.STATE_FAILED)

        dlq = self.broker.published(settings.PULSE_STREAM_DLQ)
        self.assertEqual(len(dlq), 1)
        self.assertEqual(dlq[0]["stage"], "report")
        self.assertEqual(dlq[0]["job_id"], str(self.job.job_id))
        # Idempotent row creation held across all retry attempts.
        self.assertEqual(DiagnosisReportHistory.objects.count(), 1)
