"""Async-friendly entrypoint into dynamic_report_service.

The legacy report generators in `all_reports` take a fully-populated
`DiagnosisReportHistory` plus a patient/user context, which historically was
assembled by the synchronous DRF views in `pulse_service.views`. This module is
the seam where that assembly happens for the async pipeline: a worker hands in
an `AnalysisJob` plus the algo result, and gets back raw PDF bytes.

The new `ReportWorker` calls this through the `ReportGenerator` Protocol (see
`pulse_service/workers/report_client.py`), which uploads the returned bytes to
B2 with a restricted ACL. URL minting (time-bound presigned) stays in the API
layer so TTLs remain controllable.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from django.db import transaction

from pulse_service.models import AnalysisJob


# Numeric model fields (FloatField) — coerced to float-or-None.
_FLOAT_FIELDS = ("heart_rate", "heart_yin")

# CharField metric/classification fields populated from the algo result.
_STR_FIELDS = (
    "primary", "secondary", "tertiary", "quaternary", "quinary",
    "carbohydrate", "protein", "fat",
    "wind_yin", "wind_yang", "heat_yin", "heat_yang",
    "humid_yin", "humid_yang", "dry_yin", "dry_yang", "cold_yin", "cold_yang",
    "vata", "pitta", "kapha",
)

_CLASSIFICATION_KEYS = ("primary", "secondary", "tertiary", "quaternary", "quinary")


def _flatten(analysis_result: Mapping[str, Any]) -> dict:
    """Flatten the stored analysis result into a single-level dict.

    The signal worker stores ``asdict(AnalysisResult)``, i.e. classification
    keys at the top level plus a nested ``extras`` mapping. Already-flat dicts
    are handled too, so callers may pass either shape.
    """
    flat: dict = {}
    extras = analysis_result.get("extras")
    if isinstance(extras, Mapping):
        flat.update(extras)
    for key, value in analysis_result.items():
        if key == "extras":
            continue
        flat[key] = value
    return flat


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str) and value.endswith("%"):
            value = value.rstrip("%")
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _mapped_fields(flat: Mapping[str, Any]) -> dict:
    fields: dict = {name: _to_str(flat.get(name)) for name in _STR_FIELDS}
    for name in _FLOAT_FIELDS:
        fields[name] = _to_float(flat.get(name))
    return fields


def _patient_age(dob: Optional[date]) -> str:
    if not dob:
        return ""
    today = date.today()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return str(years)


def _ensure_report_history(job: AnalysisJob, flat: Mapping[str, Any]):
    """Idempotently create the PulseData + DiagnosisReportHistory rows.

    Keyed on deterministic per-job values (the signal object key, and the pulse
    FK) so report retries reuse the same rows instead of duplicating them.
    Returns the persisted DiagnosisReportHistory.

    Concurrency contract: callers must hold the ``pulse:job:{job_id}:report``
    lock for the duration of this call. The ``get_or_create`` pair below is
    NOT atomic against a concurrent peer hitting the same job — two workers
    inside the get-but-not-found window would each insert. ``ReportWorker``
    enforces this by wrapping the whole report stage in
    ``lock_with_heartbeat``; if you call this from another seam, take the
    same lock first or add a unique constraint on ``PulseData.pulse_uri``.
    """
    from pulse_service.models import PulseData
    from report_service.models import DiagnosisReportHistory

    signal_text = ""
    if job.signal_object_key:
        try:
            from bucket_extentions.s3 import fetch_bytes

            signal_text = fetch_bytes(job.signal_object_key).decode("utf-8", "replace")
        except Exception:
            # Signal text only feeds an optional plot; absence must not block
            # report generation. The render path tolerates empty signal_data.
            signal_text = ""

    pulse_uri = job.signal_object_key or f"pulse_signals/{job.job_id}.txt"

    with transaction.atomic():
        pulse, _ = PulseData.objects.get_or_create(
            pulse_uri=pulse_uri,
            defaults={
                "signal_data": signal_text,
                "patient": job.patient,
                "user": job.user,
            },
        )
        report_history, _ = DiagnosisReportHistory.objects.get_or_create(
            pulse_id=pulse,
            user_id=job.user,
            defaults={"patient_id": job.patient, **_mapped_fields(flat)},
        )
    return report_history


def build_report_pdf(job: AnalysisJob, analysis_result: Mapping[str, Any]) -> bytes:
    """Generate the PDF bytes for the given job and algo result.

    Persists a real DiagnosisReportHistory row (idempotent across retries),
    then renders the diagnostic report to bytes via
    ``all_reports.render_pattern_pdf_bytes``. Raises on any failure — the
    ReportWorker treats exceptions as transient and retries with exponential
    backoff before routing to the DLQ.
    """
    from dynamic_report_service.all_reports import render_pattern_pdf_bytes

    flat = _flatten(analysis_result)
    report_history = _ensure_report_history(job, flat)

    parameters: dict = {key: (flat.get(key) or "") for key in _CLASSIFICATION_KEYS}
    parameters["report_type_override"] = "default"

    patient = job.patient
    patient_name = f"{patient.first_name} {patient.last_name}".strip()
    user_name = getattr(job.user, "email", None) or str(job.user)

    return render_pattern_pdf_bytes(
        report_history,
        parameters,
        user_name=user_name,
        patient_name=patient_name or "Unknown Patient",
        patient_age=_patient_age(getattr(patient, "dob", None)),
        patient_number=getattr(patient, "phone_number", "") or "",
    )
