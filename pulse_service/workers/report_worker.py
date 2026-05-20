from __future__ import annotations

import logging
import time
from typing import Optional, Sequence

from django.conf import settings

from global_utils.distributed_lock import LockAcquireError, lock
from global_utils.event_broker import EventBroker, Message, get_broker
from pulse_service.models import AnalysisJob

from .base import WorkerLoop
from .report_client import ReportGenerator, get_report_generator


log = logging.getLogger(__name__)


class ReportWorker:
    """Consumes pulse.analysis_complete, generates the PDF with retry+DLQ."""

    def __init__(
        self,
        broker: Optional[EventBroker] = None,
        generator: Optional[ReportGenerator] = None,
        retry_delays: Optional[Sequence[float]] = None,
        sleep=time.sleep,  # injection point for tests
    ):
        self.broker = broker or get_broker()
        self.generator = generator or get_report_generator()
        self.retry_delays = tuple(retry_delays or settings.PULSE_REPORT_RETRY_DELAYS)
        self._sleep = sleep
        self.loop = WorkerLoop(
            stream=settings.PULSE_STREAM_ANALYSIS_COMPLETE,
            group=settings.PULSE_REPORT_GROUP,
            handler=self._handle,
            broker=self.broker,
        )

    def run_forever(self) -> None:
        self.loop.install_signal_handlers()
        self.loop.run_forever()

    def _handle(self, message: Message) -> None:
        job_id = message.payload.get("job_id")
        if not job_id:
            log.error("dropping malformed pulse.analysis_complete id=%s", message.message_id)
            self.broker.ack(message.stream, settings.PULSE_REPORT_GROUP, message.message_id)
            return

        lock_key = f"pulse:job:{job_id}:report"
        try:
            with lock(lock_key, ttl_ms=settings.PULSE_LOCK_TTL_MS):
                self._process(job_id, message)
        except LockAcquireError:
            log.info("report lock for %s held by peer — ack and skip", job_id)
            self.broker.ack(message.stream, settings.PULSE_REPORT_GROUP, message.message_id)

    def _process(self, job_id: str, message: Message) -> None:
        try:
            job = AnalysisJob.objects.get(job_id=job_id)
        except AnalysisJob.DoesNotExist:
            log.error("report job %s not found — ack and drop", job_id)
            self.broker.ack(message.stream, settings.PULSE_REPORT_GROUP, message.message_id)
            return

        if job.state in (AnalysisJob.STATE_COMPLETED, AnalysisJob.STATE_FAILED):
            self.broker.ack(message.stream, settings.PULSE_REPORT_GROUP, message.message_id)
            return

        if job.state == AnalysisJob.STATE_ANALYSIS_COMPLETE:
            job.transition_to(AnalysisJob.STATE_REPORT_GENERATING)
        elif job.state != AnalysisJob.STATE_REPORT_GENERATING:
            log.warning(
                "report event for job %s in unexpected state %s — acking",
                job_id, job.state,
            )
            self.broker.ack(message.stream, settings.PULSE_REPORT_GROUP, message.message_id)
            return

        last_error: Optional[BaseException] = None
        attempts = len(self.retry_delays) + 1
        for attempt in range(1, attempts + 1):
            try:
                object_key = self.generator(job, job.analysis_result or {})
            except Exception as exc:
                last_error = exc
                log.warning(
                    "report attempt %d/%d failed for job %s: %r",
                    attempt, attempts, job_id, exc,
                )
                if attempt < attempts:
                    self._sleep(self.retry_delays[attempt - 1])
                continue

            job.transition_to(
                AnalysisJob.STATE_COMPLETED,
                report_object_key=object_key,
            )
            self.broker.ack(message.stream, settings.PULSE_REPORT_GROUP, message.message_id)
            return

        code = type(last_error).__name__ if last_error else "report_unknown"
        msg = repr(last_error) if last_error else "exhausted retries"
        try:
            job.transition_to(
                AnalysisJob.STATE_FAILED,
                error_code=code,
                error_message=msg,
            )
        except AnalysisJob.IllegalTransition:
            log.exception("illegal failure transition from %s", job.state)
        self.broker.move_to_dlq(
            original_stream=message.stream,
            group=settings.PULSE_REPORT_GROUP,
            message_id=message.message_id,
            dlq_stream=settings.PULSE_STREAM_DLQ,
            reason_payload={
                "job_id": str(job.job_id),
                "stage": "report",
                "error_code": code,
                "error_message": msg,
                "original_stream": message.stream,
            },
        )
