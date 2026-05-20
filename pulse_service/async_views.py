"""Async pulse pipeline HTTP surface.

Two endpoints:
- POST /pulse/jobs/         — enqueue an analysis (idempotent by token)
- GET  /pulse/jobs/<job_id>/status — strict-schema status, presigned URL when done
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from bucket_extentions.s3 import generate_presigned_url, upload_bytes_with_acl
from global_utils.distributed_lock import LockAcquireError, lock
from global_utils.event_broker import get_broker
from patients.models import PatientsModel
from pulse_service.models import AnalysisJob


log = logging.getLogger(__name__)


def _isoformat(dt) -> str:
    return dt.replace(microsecond=int(dt.microsecond / 1000) * 1000).isoformat()


def _build_status_payload(job: AnalysisJob) -> dict:
    report_url: Optional[str] = None
    if job.state == AnalysisJob.STATE_COMPLETED and job.report_object_key:
        try:
            report_url = generate_presigned_url(
                job.report_object_key, ttl_seconds=settings.PULSE_PRESIGN_TTL_SECONDS
            )
        except Exception:
            log.exception("presign failed for job=%s key=%s", job.job_id, job.report_object_key)

    return {
        "job_id": str(job.job_id),
        "patient_id": str(job.patient_id),
        "status": job.state,
        "updated_at": _isoformat(job.updated_at),
        "report_url": report_url,
        "error_metrics": {
            "code": job.error_code,
            "message": job.error_message,
        },
    }


class SubmitAnalysisJobView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        signal_data = request.data.get("signal_data")
        patient_id = request.data.get("patient_id")
        language = (request.data.get("language") or "english").strip().lower()
        idempotency_token = (
            request.headers.get("Idempotency-Key")
            or request.data.get("idempotency_token")
        )
        if not signal_data:
            return Response({"detail": "signal_data is required"}, status=400)
        if not patient_id:
            return Response({"detail": "patient_id is required"}, status=400)
        if not idempotency_token:
            return Response(
                {"detail": "idempotency_token (or Idempotency-Key header) is required"},
                status=400,
            )

        patient = PatientsModel.objects.filter(id=patient_id).first()
        if not patient or patient.user_profile != request.user:
            return Response({"detail": "patient not found"}, status=404)

        # Refusal-style lock: concurrent submits with the same token converge on one job.
        lock_key = f"pulse:idem:{idempotency_token}"
        try:
            with lock(lock_key, ttl_ms=settings.PULSE_LOCK_TTL_MS):
                existing = AnalysisJob.objects.filter(
                    idempotency_token=idempotency_token
                ).first()
                if existing:
                    return Response(
                        {"job_id": str(existing.job_id), "status": existing.state},
                        status=status.HTTP_200_OK,
                    )
                return self._create_and_publish(
                    request.user, patient, idempotency_token, signal_data, language
                )
        except LockAcquireError:
            # A peer holds the lock. They will create (or have created) the row;
            # surface the row if visible, otherwise 409 so the client can retry.
            existing = AnalysisJob.objects.filter(
                idempotency_token=idempotency_token
            ).first()
            if existing:
                return Response(
                    {"job_id": str(existing.job_id), "status": existing.state},
                    status=status.HTTP_200_OK,
                )
            return Response({"detail": "concurrent submit in progress"}, status=409)

    def _create_and_publish(self, user, patient, token, signal_data, language):
        job_id = uuid.uuid4()
        signal_bytes = signal_data.encode("utf-8") if isinstance(signal_data, str) else (
            str(signal_data).encode("utf-8")
        )
        signal_key = f"pulse_signals/{job_id}.txt"
        upload_bytes_with_acl(
            signal_bytes, signal_key, content_type="text/plain", private=True
        )

        try:
            with transaction.atomic():
                job = AnalysisJob.objects.create(
                    job_id=job_id,
                    patient=patient,
                    user=user,
                    idempotency_token=token,
                    state=AnalysisJob.STATE_RECEIVED,
                    language=language,
                    signal_object_key=signal_key,
                )
        except IntegrityError:
            # Another submitter beat us through the unique constraint after we
            # passed the visibility check above. Return the winner's row.
            existing = AnalysisJob.objects.get(idempotency_token=token)
            return Response(
                {"job_id": str(existing.job_id), "status": existing.state},
                status=status.HTTP_200_OK,
            )

        get_broker().publish(
            settings.PULSE_STREAM_RECEIVED,
            {
                "job_id": str(job.job_id),
                "patient_id": str(job.patient_id),
                "user_id": user.id,
                "signal_object_key": signal_key,
                "language": language,
                "idempotency_token": token,
            },
        )
        return Response(
            {"job_id": str(job.job_id), "status": job.state},
            status=status.HTTP_202_ACCEPTED,
        )


class AnalysisJobStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: str):
        try:
            job = AnalysisJob.objects.select_related("patient").get(job_id=job_id)
        except (AnalysisJob.DoesNotExist, ValueError):
            return Response({"detail": "job not found"}, status=404)
        if job.user_id != request.user.id and not request.user.is_superuser:
            return Response({"detail": "forbidden"}, status=403)
        return Response(_build_status_payload(job), status=200)
