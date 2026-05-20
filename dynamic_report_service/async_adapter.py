"""Async-friendly entrypoint into dynamic_report_service.

The legacy report generators (`all_reports.generate_pdf_for_pattern`,
`generate_treatment_report`) take a fully-populated `DiagnosisReportHistory`
plus a patient/user context, which today is assembled by the synchronous
DRF views in `pulse_service.views`. This module is the seam where that
assembly happens for the async pipeline: a worker hands in an AnalysisJob
plus the algo result, and gets back raw PDF bytes.

Implementation is intentionally left as a stub. Wiring it up requires
deciding which legacy fields are derivable from the analysis result alone
(no user answers) and which require user follow-up. The new ReportWorker
calls this through the ReportGenerator Protocol, so tests can swap it
out — see pulse_service/workers/report_client.py.
"""
from __future__ import annotations

from typing import Mapping

from pulse_service.models import AnalysisJob


class AsyncAdapterNotConfigured(RuntimeError):
    pass


def build_report_pdf(job: AnalysisJob, analysis_result: Mapping[str, object]) -> bytes:
    """Generate the PDF bytes for the given job and algo result.

    Replace this stub by:
      1. Creating (or fetching) a DiagnosisReportHistory from analysis_result.
      2. Calling `dynamic_report_service.all_reports.generate_pdf_for_pattern`
         with the assembled context.
      3. Reading the returned BytesIO into a `bytes` object and returning it.
    Raise on any failure — the ReportWorker treats exceptions as transient
    and retries with exponential backoff before routing to the DLQ.
    """
    raise AsyncAdapterNotConfigured(
        "dynamic_report_service.async_adapter.build_report_pdf is not wired up. "
        "Implement it or inject a custom ReportGenerator via "
        "pulse_service.workers.report_client.set_report_generator_for_tests."
    )
