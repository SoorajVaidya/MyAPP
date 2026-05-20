from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Protocol, runtime_checkable

import redis
from redis.exceptions import ResponseError

from global_utils.redis_client import get_redis


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    message_id: str
    stream: str
    payload: Mapping[str, Any]


@runtime_checkable
class EventBroker(Protocol):
    def publish(self, stream: str, payload: Mapping[str, Any]) -> str: ...

    def ensure_group(self, stream: str, group: str) -> None: ...

    def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int,
        block_ms: int,
    ) -> List[Message]: ...

    def ack(self, stream: str, group: str, message_id: str) -> None: ...

    def move_to_dlq(
        self,
        original_stream: str,
        group: str,
        message_id: str,
        dlq_stream: str,
        reason_payload: Mapping[str, Any],
    ) -> None: ...


class RedisStreamsBroker:
    """Redis Streams implementation of EventBroker.

    Payloads are JSON-encoded into a single 'data' field — keeps schema simple
    and avoids stringification surprises with nested dicts.
    """

    def __init__(self, client: Optional[redis.Redis] = None):
        self._client = client or get_redis()
        self._known_groups: set[tuple[str, str]] = set()
        self._groups_lock = threading.Lock()

    def publish(self, stream: str, payload: Mapping[str, Any]) -> str:
        body = json.dumps(dict(payload), separators=(",", ":"), default=str)
        return self._client.xadd(stream, {"data": body})

    def ensure_group(self, stream: str, group: str) -> None:
        cache_key = (stream, group)
        if cache_key in self._known_groups:
            return
        with self._groups_lock:
            if cache_key in self._known_groups:
                return
            try:
                self._client.xgroup_create(stream, group, id="0", mkstream=True)
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
            self._known_groups.add(cache_key)

    def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int,
        block_ms: int,
    ) -> List[Message]:
        self.ensure_group(stream, group)
        result = self._client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )
        if not result:
            return []
        messages: List[Message] = []
        for _stream_name, entries in result:
            for message_id, fields in entries:
                raw = fields.get("data", "{}")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    log.exception("malformed payload on %s id=%s", stream, message_id)
                    payload = {"_malformed": raw}
                messages.append(
                    Message(message_id=message_id, stream=stream, payload=payload)
                )
        return messages

    def ack(self, stream: str, group: str, message_id: str) -> None:
        self._client.xack(stream, group, message_id)

    def move_to_dlq(
        self,
        original_stream: str,
        group: str,
        message_id: str,
        dlq_stream: str,
        reason_payload: Mapping[str, Any],
    ) -> None:
        self.publish(dlq_stream, reason_payload)
        self.ack(original_stream, group, message_id)


_default: Optional[EventBroker] = None
_default_lock = threading.Lock()


def get_broker() -> EventBroker:
    global _default
    if _default is not None:
        return _default
    with _default_lock:
        if _default is None:
            _default = RedisStreamsBroker()
    return _default


def set_broker_for_tests(broker: Optional[EventBroker]) -> None:
    global _default
    _default = broker


__all__: Iterable[str] = (
    "Message",
    "EventBroker",
    "RedisStreamsBroker",
    "get_broker",
    "set_broker_for_tests",
)
