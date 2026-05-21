"""Transition atomicity tests.

`AnalysisJob.transition_to` now refetches under SELECT FOR UPDATE before
validating. Two concurrent paths racing on the same row will serialize on the
row lock, and the second one observes the first's committed state — so an
illegal follow-up transition (e.g. FAILED -> PROCESSING_SIGNAL) is rejected
rather than silently overwriting.
"""
from __future__ import annotations

import threading

from django.contrib.auth import get_user_model
from django.db import close_old_connections, transaction
from django.test import TransactionTestCase

from pulse_service.models import AnalysisJob

from .fixtures import make_user_and_patient


User = get_user_model()


class TransitionAtomicTests(TransactionTestCase):
    """Uses TransactionTestCase because the safety guarantee depends on a real
    DB transaction (savepoints in plain TestCase don't exercise row locks)."""

    def test_concurrent_failed_then_advance_raises(self) -> None:
        user, patient = make_user_and_patient(email="tx@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="tx-tok",
            state=AnalysisJob.STATE_RECEIVED,
            signal_object_key="pulse_signals/tx.txt",
        )

        # First path marks the job FAILED.
        job.transition_to(
            AnalysisJob.STATE_FAILED, error_code="test", error_message="bye"
        )

        # A stale in-memory copy (e.g. another worker that read the row
        # before the FAILED write committed) attempts an advance — refetch
        # under FOR UPDATE must see FAILED and reject.
        stale = AnalysisJob.objects.get(pk=job.pk)
        stale.state = AnalysisJob.STATE_RECEIVED  # pretend our copy is stale
        with self.assertRaises(AnalysisJob.IllegalTransition):
            stale.transition_to(AnalysisJob.STATE_PROCESSING_SIGNAL)

        # Persisted state did not regress.
        fresh = AnalysisJob.objects.get(pk=job.pk)
        self.assertEqual(fresh.state, AnalysisJob.STATE_FAILED)

    def test_transition_to_syncs_in_memory_copy(self) -> None:
        user, patient = make_user_and_patient(email="tx2@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="tx2-tok",
            state=AnalysisJob.STATE_RECEIVED,
            signal_object_key="pulse_signals/tx2.txt",
        )
        job.transition_to(AnalysisJob.STATE_PROCESSING_SIGNAL)
        self.assertEqual(job.state, AnalysisJob.STATE_PROCESSING_SIGNAL)
        job.transition_to(
            AnalysisJob.STATE_ANALYSIS_COMPLETE,
            analysis_result={"primary": "Wind"},
        )
        self.assertEqual(job.state, AnalysisJob.STATE_ANALYSIS_COMPLETE)
        self.assertEqual(job.analysis_result, {"primary": "Wind"})

    def test_terminal_state_rejects_any_transition(self) -> None:
        user, patient = make_user_and_patient(email="tx3@example.com")
        job = AnalysisJob.objects.create(
            patient=patient,
            user=user,
            idempotency_token="tx3-tok",
            state=AnalysisJob.STATE_COMPLETED,
        )
        for target in AnalysisJob.STATE_CHOICES:
            target_state = target[0]
            with self.assertRaises(AnalysisJob.IllegalTransition):
                job.transition_to(target_state)
