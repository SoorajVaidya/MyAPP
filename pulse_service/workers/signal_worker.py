from __future__ import annotations

import logging
from concurrent.futures import Executor, Future, ProcessPoolExecutor
from dataclasses import asdict
from typing import Callable, Optional

from django.conf import settings

from bucket_extentions.s3 import fetch_bytes
from global_utils.distributed_lock import (
    LockAcquireError,
    LockLostError,
    lock_with_heartbeat,
)
from global_utils.event_broker import EventBroker, Message, get_broker
from global_utils.log_context import bind, install_filter
from pulse_analysis_algo.api import AnalysisError, run_analysis
from pulse_service.models import AnalysisJob

from .base import WorkerLoop


log = logging.getLogger(__name__)


def _run_in_process(signal_bytes: bytes) -> dict:
    """Top-level callable executed inside the ProcessPool worker.

    Module-level (not a lambda or closure) so it's picklable for fork-based pools.
    """
    text = signal_bytes.decode("utf-8") if isinstance(signal_bytes, (bytes, bytearray)) else signal_bytes
    return asdict(run_analysis(text))


class SignalWorker:
    """Consumes pulse.received, runs the algo in a process pool, advances state."""

    def __init__(
        self,
        broker: Optional[EventBroker] = None,
        pool: Optional[Executor] = None,
        analyze: Callable[[bytes], dict] = _run_in_process,
    ):
        self.broker = broker or get_broker()
        self.pool = pool or ProcessPoolExecutor(max_workers=settings.PULSE_WORKER_POOL_SIZE)
        self._analyze = analyze
        self.loop = WorkerLoop(
            stream=settings.PULSE_STREAM_RECEIVED,
            group=settings.PULSE_SIGNAL_GROUP,
            handler=self._handle,
            broker=self.broker,
        )

    def run_forever(self) -> None:
        install_filter()
        self.loop.install_signal_handlers()
        try:
            self.loop.run_forever()
        finally:
            self.pool.shutdown(wait=True, cancel_futures=True)

    def _handle(self, message: Message) -> None:
        payload = message.payload
        job_id = payload.get("job_id")
        if not job_id:
            log.error("dropping malformed pulse.received id=%s", message.message_id)
            self.broker.ack(message.stream, settings.PULSE_SIGNAL_GROUP, message.message_id)
            return

        with bind(job_id=job_id, stage="signal", consumer=self.loop.consumer_name):
            lock_key = f"pulse:job:{job_id}:signal"
            try:
                with lock_with_heartbeat(
                    lock_key, ttl_ms=settings.PULSE_LOCK_TTL_MS
                ) as held:
                    self._process(job_id, message, held)
            except LockAcquireError:
                log.info("job %s already locked by another worker — ack and skip", job_id)
                self.broker.ack(
                    message.stream, settings.PULSE_SIGNAL_GROUP, message.message_id
                )
            except LockLostError:
                # Heartbeat lost the key mid-process: do NOT ack — let the pending
                # message be reclaimed by another consumer rather than silently dropping it.
                log.warning(
                    "lock for job %s was lost; leaving message pending for reclaim",
                    job_id,
                )

    def _process(self, job_id: str, message: Message, held=None) -> None:
        try:
            job = AnalysisJob.objects.get(job_id=job_id)
        except AnalysisJob.DoesNotExist:
            log.error("job %s not found — acking and dropping", job_id)
            self.broker.ack(message.stream, settings.PULSE_SIGNAL_GROUP, message.message_id)
            return

        if job.state in (AnalysisJob.STATE_ANALYSIS_COMPLETE,
                          AnalysisJob.STATE_REPORT_GENERATING,
                          AnalysisJob.STATE_COMPLETED):
            log.info("job %s already past signal stage (state=%s) — ack and skip", job_id, job.state)
            self.broker.ack(message.stream, settings.PULSE_SIGNAL_GROUP, message.message_id)
            return

        if job.state == AnalysisJob.STATE_FAILED:
            self.broker.ack(message.stream, settings.PULSE_SIGNAL_GROUP, message.message_id)
            return

        if job.state == AnalysisJob.STATE_RECEIVED:
            job.transition_to(AnalysisJob.STATE_PROCESSING_SIGNAL)

        if not job.signal_object_key:
            self._fail(job, message, code="signal_missing", msg="job has no signal_object_key")
            return
        try:
            signal_bytes = fetch_bytes(job.signal_object_key)
        except Exception as exc:
            self._fail(job, message, code="signal_fetch_failed",
                       msg=f"could not fetch {job.signal_object_key}: {exc!r}")
            return

        future: Future = self.pool.submit(self._analyze, signal_bytes)
        try:
            result_dict = future.result()
        except AnalysisError as exc:
            self._fail(job, message, code="analysis_error", msg=str(exc))
            return
        except Exception as exc:
            self._fail(job, message, code="analysis_crash", msg=repr(exc))
            return

        # If the heartbeat dropped while the algo ran, another worker may now
        # own the key. Bail without acking or writing state — the broker's
        # pending-message reclaim path will redeliver this to a healthy worker.
        if held is not None:
            held.check()

        job.transition_to(
            AnalysisJob.STATE_ANALYSIS_COMPLETE,
            analysis_result=result_dict,
        )
        self.broker.publish(
            settings.PULSE_STREAM_ANALYSIS_COMPLETE,
            {"job_id": job_id},
        )
        self.broker.ack(message.stream, settings.PULSE_SIGNAL_GROUP, message.message_id)

    def _fail(self, job: AnalysisJob, message: Message, *, code: str, msg: str) -> None:
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
            group=settings.PULSE_SIGNAL_GROUP,
            message_id=message.message_id,
            dlq_stream=settings.PULSE_STREAM_DLQ,
            reason_payload={
                "job_id": str(job.job_id),
                "stage": "signal",
                "error_code": code,
                "error_message": msg,
                "original_stream": message.stream,
            },
        )
