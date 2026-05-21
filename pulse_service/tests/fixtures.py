"""Shared fixtures for the async-pipeline test suites.

Lives under ``pulse_service.tests`` because that's where the related fakes
(``InMemoryBroker``, ``InMemoryLockKV``) live; the other apps that exercise
the pulse pipeline (dynamic_report_service, etc.) import from here so the
helpers do not drift in two copies.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Tuple

from django.contrib.auth import get_user_model

from patients.models import PatientsModel


User = get_user_model()


def make_user_and_patient(email: str = "t@example.com") -> Tuple[object, PatientsModel]:
    """Create a User + Patient pair for use in async-pipeline tests.

    ``User.phone_number`` is ``max_length=15`` and ``unique=True``; we hash the
    email to a 14-char prefix so the same email always maps to the same phone
    (deterministic across calls in one test) and distinct emails cannot
    collide on the unique constraint after truncation.
    """
    phone = hashlib.md5(email.encode()).hexdigest()[:14]
    user = User.objects.create(email=email, phone_number=phone)
    patient = PatientsModel.objects.create(
        user_profile=user,
        first_name="Test",
        last_name="Patient",
        gender="M",
        dob=date(1990, 1, 1),
        phone_number="9999999999",
        country="X",
        state="Y",
        city="Z",
        email=email + ".pat",
    )
    return user, patient
