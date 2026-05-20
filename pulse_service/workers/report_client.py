from __future__ import annotations

import logging
from typing import Mapping, Optional, Protocol, runtime_checkable

from pulse_service.models import AnalysisJob


log = logging.getLogger(__name__)


class ReportError(Exception):
    """Raised by ReportGenerator when generation fails.

    The worker treats ReportError as transient: it will retry the same job up
    to the configured number of attempts before routing to the DLQ. Any other
    exception type is treated the same way at this layer — the retry policy is
    "any failure is retried up to N times", which keeps the surface minimal
    while still bounding work.
    """


@runtime_checkable
class ReportGenerator(Protocol):
    """Pluggable report-generation boundary.

    Implementations must be transport-agnostic (no DRF request objects) and
    return the storage object key for the uploaded PDF, not a URL. URL minting
    is the API layer's job so that TTL stays controllable.
    """

    def __call__(self, job: AnalysisJob, analysis_result: Mapping[str, object]) -> str: ...


class _DjangoReportGenerator:
    """Default implementation backed by dynamic_report_service.

    The existing report pipeline is request/response shaped — we only need the
    parts that take an AnalysisJob + algo result and produce a PDF on B2. This
    class is the seam between the new async flow and the legacy generator: as
    the legacy code is refactored, only this class needs to change.
    """

    def __call__(self, job: AnalysisJob, analysis_result: Mapping[str, object]) -> str:
        from bucket_extentions.s3 import upload_bytes_with_acl
        from dynamic_report_service.async_adapter import build_report_pdf

        try:
            pdf_bytes = build_report_pdf(job, analysis_result)
        except Exception as exc:
            raise ReportError(f"report build failed: {exc!r}") from exc

        object_key = f"reports/{job.job_id}.pdf"
        upload_bytes_with_acl(pdf_bytes, object_key, content_type="application/pdf", private=True)
        return object_key


_default: Optional[ReportGenerator] = None


def get_report_generator() -> ReportGenerator:
    global _default
    if _default is None:
        _default = _DjangoReportGenerator()
    return _default


def set_report_generator_for_tests(generator: Optional[ReportGenerator]) -> None:
    global _default
    _default = generator
