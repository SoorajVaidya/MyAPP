from __future__ import annotations

from typing import Literal, TypedDict


JobState = Literal[
    "RECEIVED",
    "PROCESSING_SIGNAL",
    "ANALYSIS_COMPLETE",
    "REPORT_GENERATING",
    "COMPLETED",
    "FAILED",
]


class PulseReceivedPayload(TypedDict):
    job_id: str
    patient_id: str
    user_id: int
    signal_object_key: str
    language: str
    idempotency_token: str


class PulseAnalysisCompletePayload(TypedDict):
    job_id: str


class PulseDLQPayload(TypedDict):
    job_id: str
    stage: Literal["signal", "report"]
    error_code: str
    error_message: str
    original_stream: str
