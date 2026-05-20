from __future__ import annotations

import secrets
import time
from contextlib import contextmanager
from typing import Iterator, Optional

import redis

from global_utils.redis_client import get_redis


_UNLOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


class LockAcquireError(RuntimeError):
    pass


class DistributedLock:
    """SET NX PX-based lock with Lua-guarded release.

    A holder owns the key only for the lifetime of its token; releasing without
    the matching token is a no-op, which is what prevents one process from
    stomping another's lock after a TTL-driven expiry.
    """

    def __init__(self, key: str, ttl_ms: int, client: Optional[redis.Redis] = None):
        self.key = key
        self.ttl_ms = ttl_ms
        self._client = client or get_redis()
        self._token: Optional[str] = None

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

    def release(self) -> bool:
        if self._token is None:
            return False
        try:
            result = self._client.eval(_UNLOCK_LUA, 1, self.key, self._token)
            return bool(result)
        finally:
            self._token = None


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
