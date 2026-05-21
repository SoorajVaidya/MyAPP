"""Concurrency & high-volume stress tests for the async pulse pipeline.

These reproduce — deterministically — the failure modes described in the
stabilization brief and assert the safeguards hold:

- Duplicate workers acquiring the same processing context: proven impossible at
  the lock layer (``LockRaceTests``) and at the worker layer under real-thread
  contention (``ConcurrentProcessingTests``).
- Duplicate report/analysis on retried or redelivered messages: a job delivered
  N times concurrently is analyzed once and fans out downstream once.
- Inconsistent state under parallel writes: many distinct jobs advanced from
  separate threads all land in the right terminal state with no lost updates.
- High-volume ingestion: a large batch flows end-to-end with exactly one
  unit of work per job and an empty DLQ.

Threading notes
---------------
The lock-layer tests need no database. The worker-layer tests use
``TransactionTestCase`` (not ``TestCase``) because each worker thread opens its
own DB connection and must see rows the main thread *committed* — a plain
``TestCase`` hides setup data inside an uncommitted transaction. We raise the
SQLite ``busy_timeout`` so the brief write-serialization window doesn't surface
as spurious "database is locked" errors, and every worker thread closes its
connection on the way out. A ``Barrier`` makes the threads contend
simultaneously so the race is real rather than incidentally serialized.
"""
from __future__ import annotations

import threading
from typing import Callable, List
from unittest import mock

from django.conf import settings
from django.db import OperationalError, connection
from django.db.backends.signals import connection_created
from django.test import SimpleTestCase, TransactionTestCase

from global_utils import event_broker as broker_module
from global_utils import redis_client as redis_client_module
from global_utils.distributed_lock import LockAcquireError, lock
from global_utils.event_broker import Message
from pulse_service.models import AnalysisJob
from pulse_service.workers.report_worker import ReportWorker
from pulse_service.workers.signal_worker import SignalWorker

from .fakes import InMemoryBroker, InMemoryLockKV, SyncExecutor
from .fixtures import make_user_and_patient


FAKE_RESULT = {
    "primary": "Wind", "secondary": "Heat", "tertiary": "Cold",
    "quaternary": "Dry", "quinary": None, "extras": {},
}


class _AtomicCounter:
    """Thread-safe call counter for assertions about how often work ran."""

    def __init__(self) -> None:
        self._n = 0
        self._lock = threading.Lock()

    def incr(self) -> None:
        with self._lock:
            self._n += 1

    @property
    def value(self) -> int:
        with self._lock:
            return self._n


def _handle_tolerating_sqlite_lock(worker, message, attempts: int = 200) -> None:
    """Drive ``worker._handle`` retrying past SQLite's coarse table lock.

    SQLite in shared-cache mode raises ``database table is locked``
    (SQLITE_LOCKED) the instant two connections write the same table — and,
    unlike SQLITE_BUSY, it is NOT subject to ``busy_timeout``. Production runs
    on PostgreSQL/MySQL where row-level locking makes concurrent writes to
    distinct rows a non-event; this retry is purely a test-backend concession
    so the genuine multi-thread contention can still be exercised. The handler
    is idempotent (state guard + per-job lock), so re-running on a lock error is
    safe — it never double-publishes.
    """
    import time

    for _ in range(attempts):
        try:
            worker._handle(message)
            return
        except OperationalError as exc:
            if "lock" not in str(exc).lower():
                raise
            time.sleep(0.01)
    raise AssertionError("gave up retrying past SQLite lock contention")


def _run_concurrently(targets: List[Callable[[], None]], timeout: float = 15.0) -> List[BaseException]:
    """Run each callable on its own thread, started simultaneously via a Barrier.

    Returns the list of exceptions raised by any thread (empty == all clean).
    Each thread closes its DB connection on exit so the test's connection pool
    doesn't leak across the TransactionTestCase truncation.
    """
    barrier = threading.Barrier(len(targets))
    errors: List[BaseException] = []
    errors_lock = threading.Lock()

    def wrap(fn: Callable[[], None]) -> Callable[[], None]:
        def inner() -> None:
            try:
                barrier.wait(timeout=timeout)
                fn()
            except BaseException as exc:  # noqa: BLE001 - surfaced to main thread
                with errors_lock:
                    errors.append(exc)
            finally:
                connection.close()
        return inner

    threads = [threading.Thread(target=wrap(fn)) for fn in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    return errors


class LockRaceTests(SimpleTestCase):
    """The distributed lock is the primitive every other safeguard rests on.

    These exercise it under genuine thread contention (no DB) so the
    winner-takes-all and never-two-at-once guarantees are pinned independent of
    the worker logic above them.
    """

    def setUp(self) -> None:
        self.kv = InMemoryLockKV()

    def test_only_one_of_many_threads_acquires_nonblocking(self) -> None:
        winners = _AtomicCounter()
        start = threading.Event()

        def attempt() -> None:
            try:
                with lock("contended", ttl_ms=5000, blocking_timeout_ms=0, client=self.kv):
                    winners.incr()
                    # Hold long enough that every peer's nonblocking attempt
                    # overlaps this critical section and is refused.
                    start.wait(timeout=0.2)
            except LockAcquireError:
                pass

        # Release holders shortly after they all start contending.
        def release_soon() -> None:
            import time
            time.sleep(0.05)
            start.set()

        releaser = threading.Thread(target=release_soon)
        releaser.start()
        errors = _run_concurrently([attempt for _ in range(25)])
        releaser.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual(winners.value, 1)

    def test_blocking_acquire_serializes_all_threads_one_at_a_time(self) -> None:
        """With a blocking timeout every thread eventually runs, but the
        in-critical-section count must never exceed 1 — mutual exclusion."""
        entered = _AtomicCounter()
        concurrent = {"now": 0, "max": 0}
        cl = threading.Lock()

        def attempt() -> None:
            with lock("serial", ttl_ms=5000, blocking_timeout_ms=4000, client=self.kv):
                entered.incr()
                with cl:
                    concurrent["now"] += 1
                    concurrent["max"] = max(concurrent["max"], concurrent["now"])
                try:
                    # tiny dwell so overlaps would be observable if they happened
                    threading.Event().wait(0.005)
                finally:
                    with cl:
                        concurrent["now"] -= 1

        errors = _run_concurrently([attempt for _ in range(10)])
        self.assertEqual(errors, [])
        self.assertEqual(entered.value, 10)      # all made progress
        self.assertEqual(concurrent["max"], 1)   # but never simultaneously


class _PipelineTestBase(TransactionTestCase):
    """Wires the in-memory broker/lock fakes and raises SQLite's busy_timeout
    so brief write serialization across worker threads doesn't flake."""

    def setUp(self) -> None:
        self.broker = InMemoryBroker()
        self.kv = InMemoryLockKV()
        broker_module.set_broker_for_tests(self.broker)
        redis_client_module.reset_for_tests(self.kv)
        connection_created.connect(self._raise_busy_timeout)
        # Apply to the already-open main connection too.
        self._raise_busy_timeout(connection=connection)

    def tearDown(self) -> None:
        connection_created.disconnect(self._raise_busy_timeout)
        broker_module.set_broker_for_tests(None)
        redis_client_module.reset_for_tests(None)

    @staticmethod
    def _raise_busy_timeout(sender=None, connection=None, **kwargs) -> None:
        if connection is not None and connection.vendor == "sqlite":
            with connection.cursor() as cur:
                cur.execute("PRAGMA busy_timeout = 8000;")


class PipelineVolumeTests(_PipelineTestBase):
    """High-volume ingestion: a batch of jobs flows signal -> report end to end
    with exactly one analysis and one report per job, and an empty DLQ."""

    N = 25

    def test_batch_flows_end_to_end_without_duplication(self) -> None:
        jobs = []
        for i in range(self.N):
            user, patient = make_user_and_patient(email=f"vol{i}@example.com")
            job = AnalysisJob.objects.create(
                patient=patient, user=user,
                idempotency_token=f"vol-{i}",
                state=AnalysisJob.STATE_RECEIVED,
                signal_object_key=f"pulse_signals/vol{i}.txt",
            )
            jobs.append(job)
            self.broker.enqueue(settings.PULSE_STREAM_RECEIVED, {"job_id": str(job.job_id)})

        analyze_calls = _AtomicCounter()

        def analyze(_bytes):
            analyze_calls.incr()
            return FAKE_RESULT

        signal_worker = SignalWorker(broker=self.broker, pool=SyncExecutor(), analyze=analyze)
        report_calls = _AtomicCounter()

        def generator(job, _result):
            report_calls.incr()
            return f"reports/{job.job_id}.pdf"

        report_worker = ReportWorker(
            broker=self.broker, generator=generator,
            retry_delays=(0.0, 0.0, 0.0), sleep=lambda _s: None,
        )

        with mock.patch("pulse_service.workers.signal_worker.fetch_bytes", return_value=b"raw"):
            for m in self.broker.consume(
                settings.PULSE_STREAM_RECEIVED, settings.PULSE_SIGNAL_GROUP, "drain",
                count=10_000, block_ms=0,
            ):
                signal_worker._handle(m)
            for m in self.broker.consume(
                settings.PULSE_STREAM_ANALYSIS_COMPLETE, settings.PULSE_REPORT_GROUP, "drain",
                count=10_000, block_ms=0,
            ):
                report_worker._handle(m)

        # Every job reached COMPLETED with a report key, exactly once each.
        completed = AnalysisJob.objects.filter(state=AnalysisJob.STATE_COMPLETED)
        self.assertEqual(completed.count(), self.N)
        self.assertEqual(analyze_calls.value, self.N)
        self.assertEqual(report_calls.value, self.N)
        self.assertEqual(len(self.broker.published(settings.PULSE_STREAM_ANALYSIS_COMPLETE)), self.N)
        self.assertEqual(self.broker.published(settings.PULSE_STREAM_DLQ), [])
        # No pending leftovers on either stream.
        self.assertEqual(self.broker.pending(settings.PULSE_STREAM_RECEIVED, settings.PULSE_SIGNAL_GROUP), [])
        self.assertEqual(self.broker.pending(settings.PULSE_STREAM_ANALYSIS_COMPLETE, settings.PULSE_REPORT_GROUP), [])


class ConcurrentProcessingTests(_PipelineTestBase):
    def test_duplicate_delivery_of_same_job_is_processed_once(self) -> None:
        """The same job delivered to several workers at once must be analyzed
        once and fan out downstream once — the per-job lock + state guard make
        the losers ack-and-skip. This is the duplicate-report scenario."""
        user, patient = make_user_and_patient(email="dup@example.com")
        job = AnalysisJob.objects.create(
            patient=patient, user=user,
            idempotency_token="dup-tok",
            state=AnalysisJob.STATE_RECEIVED,
            signal_object_key="pulse_signals/dup.txt",
        )

        analyze_calls = _AtomicCounter()

        def analyze(_bytes):
            analyze_calls.incr()
            # Dwell so the contending threads genuinely overlap on the lock.
            threading.Event().wait(0.02)
            return FAKE_RESULT

        worker = SignalWorker(broker=self.broker, pool=SyncExecutor(), analyze=analyze)

        # Five independent deliveries of the SAME logical job (original +
        # reclaims/redeliveries), each its own message id.
        messages = [
            Message(message_id=f"m{i}", stream=settings.PULSE_STREAM_RECEIVED,
                    payload={"job_id": str(job.job_id)})
            for i in range(5)
        ]

        with mock.patch("pulse_service.workers.signal_worker.fetch_bytes", return_value=b"raw"):
            errors = _run_concurrently([
                (lambda m=m: worker._handle(m)) for m in messages
            ])

        self.assertEqual(errors, [])
        job.refresh_from_db()
        self.assertEqual(job.state, AnalysisJob.STATE_ANALYSIS_COMPLETE)
        self.assertEqual(analyze_calls.value, 1)  # analyzed exactly once
        downstream = self.broker.published(settings.PULSE_STREAM_ANALYSIS_COMPLETE)
        self.assertEqual(len(downstream), 1)      # fanned out exactly once
        self.assertEqual(downstream[0]["job_id"], str(job.job_id))

    def test_many_distinct_jobs_processed_in_parallel(self) -> None:
        """Distinct jobs (distinct lock keys) advanced from separate threads
        produce real concurrent DB writes; every row must land in the correct
        state with no lost updates or cross-talk."""
        N = 6
        jobs = []
        for i in range(N):
            user, patient = make_user_and_patient(email=f"par{i}@example.com")
            job = AnalysisJob.objects.create(
                patient=patient, user=user,
                idempotency_token=f"par-{i}",
                state=AnalysisJob.STATE_RECEIVED,
                signal_object_key=f"pulse_signals/par{i}.txt",
            )
            jobs.append(job)

        analyze_calls = _AtomicCounter()

        def analyze(_bytes):
            analyze_calls.incr()
            return FAKE_RESULT

        worker = SignalWorker(broker=self.broker, pool=SyncExecutor(), analyze=analyze)
        messages = [
            Message(message_id=f"d{i}", stream=settings.PULSE_STREAM_RECEIVED,
                    payload={"job_id": str(job.job_id)})
            for i, job in enumerate(jobs)
        ]

        with mock.patch("pulse_service.workers.signal_worker.fetch_bytes", return_value=b"raw"):
            errors = _run_concurrently([
                (lambda m=m: _handle_tolerating_sqlite_lock(worker, m)) for m in messages
            ])

        self.assertEqual(errors, [])
        # Every distinct job converged to ANALYSIS_COMPLETE with no lost updates.
        self.assertEqual(
            AnalysisJob.objects.filter(state=AnalysisJob.STATE_ANALYSIS_COMPLETE).count(), N
        )
        # Exactly one downstream fan-out per distinct job — no duplicates and no
        # cross-talk between rows even under genuine parallel processing. (A
        # SQLite lock retry may re-run analyze, so we assert >= N, not == N; the
        # publish-once guarantee below is the real invariant.)
        self.assertGreaterEqual(analyze_calls.value, N)
        published = self.broker.published(settings.PULSE_STREAM_ANALYSIS_COMPLETE)
        published_ids = [p["job_id"] for p in published]
        self.assertEqual(sorted(published_ids), sorted(str(j.job_id) for j in jobs))
        self.assertEqual(len(published_ids), len(set(published_ids)))  # no dup publishes
