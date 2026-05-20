from __future__ import annotations

import logging
import signal
import socket
import threading
import time
from typing import Callable, Optional

from django.conf import settings

from global_utils.event_broker import EventBroker, Message, get_broker


log = logging.getLogger(__name__)


Handler = Callable[[Message], None]


def make_consumer_name(prefix: str) -> str:
    return f"{prefix}-{socket.gethostname()}-{threading.get_ident()}"


class WorkerLoop:
    """Generic consumer-group loop with graceful shutdown.

    Handlers either return normally (we ack) or raise (we let the message stay
    in the pending list for the worker to handle the retry/DLQ semantics it
    needs — base loop has no opinion).
    """

    def __init__(
        self,
        stream: str,
        group: str,
        handler: Handler,
        broker: Optional[EventBroker] = None,
        consumer_name: Optional[str] = None,
        batch_size: int = 8,
        block_ms: int = 5000,
    ):
        self.stream = stream
        self.group = group
        self.handler = handler
        self.broker = broker or get_broker()
        self.consumer_name = consumer_name or make_consumer_name(group)
        self.batch_size = batch_size
        self.block_ms = block_ms
        self._stop = threading.Event()

    def stop(self, *_args) -> None:
        log.info("worker %s stop requested", self.consumer_name)
        self._stop.set()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def run_forever(self) -> None:
        self.broker.ensure_group(self.stream, self.group)
        log.info(
            "worker %s consuming stream=%s group=%s",
            self.consumer_name,
            self.stream,
            self.group,
        )
        while not self._stop.is_set():
            try:
                messages = self.broker.consume(
                    stream=self.stream,
                    group=self.group,
                    consumer=self.consumer_name,
                    count=self.batch_size,
                    block_ms=self.block_ms,
                )
            except Exception:
                log.exception("consume error on %s; backing off", self.stream)
                time.sleep(1.0)
                continue
            for message in messages:
                if self._stop.is_set():
                    break
                try:
                    self.handler(message)
                except Exception:
                    log.exception(
                        "unhandled handler error stream=%s id=%s — message NOT acked",
                        message.stream,
                        message.message_id,
                    )
        log.info("worker %s stopped", self.consumer_name)
