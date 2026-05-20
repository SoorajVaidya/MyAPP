"""Test-only Django settings.

Imports prod settings and overrides the bits that hardcode MySQL: the
`init_command` option is MySQL-specific and breaks under SQLite. We also
force an in-memory SQLite DB so test runs don't need a live database server.
"""
from .settings import *  # noqa: F401,F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Silence DEBUG churn during test runs.
DEBUG = False
