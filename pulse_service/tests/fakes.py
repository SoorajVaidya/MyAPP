"""In-process doubles used by the async-pipeline tests.

Goal: exercise the broker/lock/worker flow without standing up Redis or a
real ProcessPool. Each fake implements just the surface its production
counterpart exposes — see EventBroker Protocol and DistributedLock contract.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import Future
from contextlib import contextmanager
from typing import Any, Deque, Dict, Iterator, List, Mapping, Optional, Tuple


class InMemoryBroker:
    """Implements the EventBroker Protocol with thread-safe in-memory queues."""

    def __init__(self) -> None:
        self._streams: Dict[str, Deque[Tuple[str, dict]]] = defaultdict(deque)
        self._pending: Dict[Tuple[str, str, str], dict] = {}
        self._published: Dict[str, List[dict]] = defaultdict(list)
        self._lock = threading.Lock()

    def publish(self, stream: str, payload: Mapping[str, Any]) -> str:
        message_id = f"{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._streams[stream].append((message_id, dict(payload)))
            self._published[stream].append(dict(payload))
        return message_id

    def ensure_group(self, stream: str, group: str) -> None:
        return None

    def consume(self, stream, group, consumer, count, block_ms):
        from global_utils.event_broker import Message

        out: List[Message] = []
        with self._lock:
            queue = self._streams[stream]
            while queue and len(out) < count:
                mid, payload = queue.popleft()
                self._pending[(stream, group, mid)] = payload
                out.append(Message(message_id=mid, stream=stream, payload=payload))
        return out

    def ack(self, stream: str, group: str, message_id: str) -> None:
        with self._lock:
            self._pending.pop((stream, group, message_id), None)

    def move_to_dlq(self, original_stream, group, message_id, dlq_stream, reason_payload):
        self.publish(dlq_stream, reason_payload)
        self.ack(original_stream, group, message_id)

    def published(self, stream: str) -> List[dict]:
        with self._lock:
            return list(self._published[stream])

    def enqueue(self, stream: str, payload: Mapping[str, Any]) -> str:
        return self.publish(stream, payload)


class InMemoryLockKV:
    """The slice of redis_client.get_redis() that the lock actually uses.

    Implements SET NX PX and the EVAL Lua release with token-equality check.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[str, float]] = {}  # key -> (token, expires_at)
        self._lock = threading.Lock()

    def _expired(self, key: str) -> bool:
        entry = self._store.get(key)
        return entry is not None and entry[1] <= time.monotonic()

    def set(self, key: str, value: str, nx: bool = False, px: Optional[int] = None) -> bool:
        with self._lock:
            if self._expired(key):
                self._store.pop(key, None)
            if nx and key in self._store:
                return False
            expires_at = time.monotonic() + (px / 1000.0) if px else float("inf")
            self._store[key] = (value, expires_at)
            return True

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if self._expired(key):
                self._store.pop(key, None)
                return None
            entry = self._store.get(key)
            return entry[0] if entry else None

    def eval(self, _script: str, _numkeys: int, key: str, token: str) -> int:
        with self._lock:
            entry = self._store.get(key)
            if entry and entry[0] == token:
                del self._store[key]
                return 1
            return 0


class SyncExecutor:
    """concurrent.futures.Executor that runs work on the calling thread.

    Lets us exercise SignalWorker.submit() without spinning up a real pool.
    """

    def submit(self, fn, /, *args, **kwargs) -> Future:
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, wait=True, cancel_futures=False) -> None:
        return None
