from __future__ import annotations

from threading import Lock
from typing import Optional

import redis
from django.conf import settings


_client: Optional[redis.Redis] = None
_client_lock = Lock()


def get_redis() -> redis.Redis:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_keepalive=True,
                health_check_interval=30,
            )
    return _client


def reset_for_tests(client: Optional[redis.Redis] = None) -> None:
    global _client
    _client = client
