"""HTTP-layer tests for the submit/status endpoints.

Idempotency is proven at the unit level (`SubmitAnalysisJobView` short-circuits
on a token hit); we still test it here because the row uniqueness constraint
+ the refusal-style lock together are what make the endpoint correct in
multi-worker deployments, and that interaction is what the test pins down.
"""
from __future__ import annotations

from datetime import date
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from global_utils import event_broker as broker_module
from global_utils import redis_client as redis_client_module
from patients.models import PatientsModel
from pulse_service.models import AnalysisJob

from .fakes import InMemoryBroker, InMemoryLockKV


User = get_user_model()


class SubmitAnalysisJobViewTests(TestCase):
    def setUp(self) -> None:
        self.broker = InMemoryBroker()
        self.kv = InMemoryLockKV()
        broker_module.set_broker_for_tests(self.broker)
        redis_client_module.reset_for_tests(self.kv)

        self.user = User.objects.create(email="u@example.com", phone_number="u_at")
        self.patient = PatientsModel.objects.create(
            user_profile=self.user,
            first_name="A", last_name="B", gender="M",
            dob=date(1990, 1, 1), phone_number="1234567890",
            country="X", state="Y", city="Z",
            email="a.b@example.com",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def tearDown(self) -> None:
        broker_module.set_broker_for_tests(None)
        redis_client_module.reset_for_tests(None)

    @mock.patch("pulse_service.async_views.upload_bytes_with_acl", return_value="ignored")
    def test_duplicate_token_returns_same_job(self, _upload) -> None:
        payload = {
            "signal_data": "1,2,3,4",
            "patient_id": self.patient.id,
            "idempotency_token": "shared-token",
            "language": "english",
        }
        first = self.client.post("/api/v1/pulse_service/jobs/", payload, format="json")
        second = self.client.post("/api/v1/pulse_service/jobs/", payload, format="json")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["job_id"], second.data["job_id"])

        # Exactly one row, exactly one publish.
        self.assertEqual(
            AnalysisJob.objects.filter(idempotency_token="shared-token").count(), 1
        )
        self.assertEqual(
            len(self.broker.published(settings.PULSE_STREAM_RECEIVED)), 1
        )

    @mock.patch("pulse_service.async_views.upload_bytes_with_acl", return_value="ignored")
    def test_missing_idempotency_token_rejected(self, _upload) -> None:
        resp = self.client.post(
            "/api/v1/pulse_service/jobs/",
            {"signal_data": "1,2,3", "patient_id": self.patient.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class AnalysisJobStatusViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create(email="s@example.com", phone_number="s_at")
        self.patient = PatientsModel.objects.create(
            user_profile=self.user,
            first_name="S", last_name="P", gender="F",
            dob=date(1990, 1, 1), phone_number="2222222222",
            country="X", state="Y", city="Z",
            email="s.p@example.com",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_schema_for_completed_job(self) -> None:
        job = AnalysisJob.objects.create(
            patient=self.patient, user=self.user,
            idempotency_token="status-tok",
            state=AnalysisJob.STATE_COMPLETED,
            report_object_key="reports/x.pdf",
        )
        with mock.patch(
            "pulse_service.async_views.generate_presigned_url",
            return_value="https://signed.example/x.pdf?sig=...",
        ):
            resp = self.client.get(f"/api/v1/pulse_service/jobs/{job.job_id}/status/")
        self.assertEqual(resp.status_code, 200)
        body = resp.data
        self.assertEqual(set(body.keys()),
                         {"job_id", "patient_id", "status", "updated_at",
                          "report_url", "error_metrics"})
        self.assertEqual(body["status"], "COMPLETED")
        self.assertEqual(body["report_url"], "https://signed.example/x.pdf?sig=...")
        self.assertEqual(body["error_metrics"], {"code": None, "message": None})

    def test_schema_for_failed_job(self) -> None:
        job = AnalysisJob.objects.create(
            patient=self.patient, user=self.user,
            idempotency_token="fail-tok",
            state=AnalysisJob.STATE_FAILED,
            error_code="downstream_oops",
            error_message="some upstream blew up",
        )
        resp = self.client.get(f"/api/v1/pulse_service/jobs/{job.job_id}/status/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "FAILED")
        self.assertIsNone(resp.data["report_url"])
        self.assertEqual(resp.data["error_metrics"]["code"], "downstream_oops")
