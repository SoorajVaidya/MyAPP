"""Process-wide logging context for async pipeline correlation.

The async pipeline crosses threads, processes, and broker hops, so debugging a
failure means stitching log lines across components. We bind a small set of
correlation fields (job_id, stage, attempt, consumer) into ``contextvars`` and
inject them onto LogRecord via a filter — emitters keep their normal logger
calls; the formatter sees the extra fields.

Usage::

    from global_utils.log_context import bind, install_filter

    log = logging.getLogger(__name__)

    with bind(job_id="...", stage="signal", attempt=1):
        log.info("processing")  # record carries job_id/stage/attempt

The filter is idempotent — call ``install_filter()`` once at process startup
(workers do this from their entrypoints) and any logger output downstream gets
the extra fields automatically.
"""
from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any, Iterator, Optional


_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("pulse_log_ctx", default={})


_FIELDS = ("job_id", "stage", "attempt", "consumer")


def get_context() -> dict:
    return dict(_ctx.get())


def set_context(**fields: Any) -> None:
    """Replace the current logging context entirely."""
    _ctx.set({k: v for k, v in fields.items() if v is not None})


@contextmanager
def bind(**fields: Any) -> Iterator[dict]:
    """Stack a logging context for the duration of the block.

    Nested binds merge with the parent; on exit we restore the parent.
    """
    parent = _ctx.get()
    merged = dict(parent)
    for key, value in fields.items():
        if value is None:
            continue
        merged[key] = value
    token = _ctx.set(merged)
    try:
        yield merged
    finally:
        _ctx.reset(token)


class _ContextFilter(logging.Filter):
    """Attach context fields to LogRecord so formatters can render them."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _ctx.get()
        for field in _FIELDS:
            # Never overwrite a field a caller explicitly set via ``extra=``.
            if not hasattr(record, field):
                setattr(record, field, ctx.get(field, "-"))
        return True


_installed = False


def install_filter(logger: Optional[logging.Logger] = None) -> None:
    """Idempotently attach the context filter to the root logger."""
    global _installed
    target = logger if logger is not None else logging.getLogger()
    if _installed and logger is None:
        return
    target.addFilter(_ContextFilter())
    if logger is None:
        _installed = True
