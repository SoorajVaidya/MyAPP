from __future__ import annotations

import logging
import secrets
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

import redis

from global_utils.redis_client import get_redis


log = logging.getLogger(__name__)


_UNLOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

# Extend the TTL only if the caller still owns the key (token equality).
# A stolen lock (TTL-expired and re-acquired by someone else) returns 0 so the
# previous owner learns it has lost ownership rather than silently stomping.
_EXTEND_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
else
    return 0
end
"""


class LockAcquireError(RuntimeError):
    pass


class LockLostError(RuntimeError):
    """Raised when a heartbeat tries to extend a lock the holder no longer owns."""


class DistributedLock:
    """SET NX PX-based lock with Lua-guarded release and extension.

    A holder owns the key only for the lifetime of its token; releasing or
    extending without the matching token is a no-op, which is what prevents
    one process from stomping another's lock after a TTL-driven expiry.
    """

    def __init__(self, key: str, ttl_ms: int, client: Optional[redis.Redis] = None):
        self.key = key
        self.ttl_ms = ttl_ms
        self._client = client or get_redis()
        self._token: Optional[str] = None

    @property
    def token(self) -> Optional[str]:
        return self._token

    def acquire(self, blocking_timeout_ms: int = 0, poll_ms: int = 50) -> bool:
        token = secrets.token_hex(16)
        deadline = time.monotonic() + (blocking_timeout_ms / 1000.0)
        while True:
            if self._client.set(self.key, token, nx=True, px=self.ttl_ms):
                self._token = token
                return True
            if blocking_timeout_ms <= 0 or time.monotonic() >= deadline:
                return False
            time.sleep(poll_ms / 1000.0)

    def extend(self, ttl_ms: Optional[int] = None) -> bool:
        """Refresh the TTL to ``ttl_ms`` (default: original ttl_ms).

        Returns True if the extension succeeded, False if the lock is no longer
        owned by this holder. Callers running a heartbeat should treat False as
        a signal to abort the work, because another worker may now own the key.
        """
        if self._token is None:
            return False
        new_ttl = ttl_ms if ttl_ms is not None else self.ttl_ms
        result = self._client.eval(_EXTEND_LUA, 1, self.key, self._token, new_ttl)
        return bool(result)

    def release(self) -> bool:
        if self._token is None:
            return False
        try:
            result = self._client.eval(_UNLOCK_LUA, 1, self.key, self._token)
            return bool(result)
        finally:
            self._token = None


class Heartbeater:
    """Background thread that periodically extends a held lock's TTL.

    The heartbeat runs at roughly ttl_ms / 3 so two consecutive misses still
    leave us inside the TTL. If an extension fails (lock was stolen after TTL
    expiry, or Redis is unreachable), ``lost_event`` is set so the work loop
    can check and abort instead of stepping on a peer's run.
    """

    def __init__(
        self,
        dl: DistributedLock,
        interval_ms: Optional[int] = None,
        ttl_ms: Optional[int] = None,
    ):
        self._dl = dl
        self._ttl_ms = ttl_ms if ttl_ms is not None else dl.ttl_ms
        self._interval = (interval_ms if interval_ms is not None else max(1000, self._ttl_ms // 3)) / 1000.0
        self._stop = threading.Event()
        self.lost_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name=f"lock-heartbeat:{self._dl.key}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self._interval * 2, 2.0))
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                ok = self._dl.extend(self._ttl_ms)
            except Exception:
                log.exception("heartbeat extend errored for key=%s", self._dl.key)
                self.lost_event.set()
                return
            if not ok:
                log.warning("heartbeat lost ownership of key=%s", self._dl.key)
                self.lost_event.set()
                return


@contextmanager
def lock(
    key: str,
    ttl_ms: int,
    blocking_timeout_ms: int = 0,
    client: Optional[redis.Redis] = None,
) -> Iterator[DistributedLock]:
    """Context-managed lock. Raises LockAcquireError on collision.

    Idempotency-by-refusal: callers that want "only one of N concurrent attempts
    proceeds" should leave blocking_timeout_ms=0 and treat LockAcquireError as
    "someone else owns this and will do the work".
    """
    dl = DistributedLock(key, ttl_ms, client=client)
    if not dl.acquire(blocking_timeout_ms=blocking_timeout_ms):
        raise LockAcquireError(f"could not acquire lock {key}")
    try:
        yield dl
    finally:
        dl.release()


@contextmanager
def lock_with_heartbeat(
    key: str,
    ttl_ms: int,
    blocking_timeout_ms: int = 0,
    heartbeat_ms: Optional[int] = None,
    client: Optional[redis.Redis] = None,
) -> Iterator["HeartbeatLock"]:
    """Context-managed lock with a background heartbeat.

    Yields a ``HeartbeatLock`` (the DistributedLock plus a Heartbeater handle).
    Callers running long work should periodically check ``hb.lost_event`` and
    bail out: continuing past a lost lock means a peer might be running the
    same work concurrently.
    """
    dl = DistributedLock(key, ttl_ms, client=client)
    if not dl.acquire(blocking_timeout_ms=blocking_timeout_ms):
        raise LockAcquireError(f"could not acquire lock {key}")
    hb = Heartbeater(dl, interval_ms=heartbeat_ms, ttl_ms=ttl_ms)
    hb.start()
    try:
        yield HeartbeatLock(dl, hb)
    finally:
        hb.stop()
        dl.release()


class HeartbeatLock:
    """Pair returned by lock_with_heartbeat. ``check()`` raises LockLostError
    if the background heartbeat has reported a lost lock since the last call.
    """

    __slots__ = ("lock", "heartbeat")

    def __init__(self, dl: DistributedLock, hb: Heartbeater):
        self.lock = dl
        self.heartbeat = hb

    @property
    def lost(self) -> bool:
        return self.heartbeat.lost_event.is_set()

    def check(self) -> None:
        if self.lost:
            raise LockLostError(f"lock {self.lock.key} was lost mid-operation")
