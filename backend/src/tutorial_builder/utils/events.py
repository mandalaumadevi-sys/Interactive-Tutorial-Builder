"""A tiny thread-safe per-run event bus for streaming progress to the UI (SSE).

The graph runs in a background thread and calls ``publish()``; the async SSE endpoint
replays history then drains the queue. No event-loop juggling — just a thread-safe Queue.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunChannel:
    history: list[dict] = field(default_factory=list)
    q: "queue.Queue[dict]" = field(default_factory=queue.Queue)
    done: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


class RunEventBus:
    def __init__(self) -> None:
        self._channels: dict[str, RunChannel] = {}
        self._lock = threading.Lock()

    def open(self, run_id: str) -> RunChannel:
        with self._lock:
            ch = self._channels.get(run_id)
            if ch is None:
                ch = RunChannel()
                self._channels[run_id] = ch
            return ch

    def get(self, run_id: str) -> RunChannel | None:
        return self._channels.get(run_id)

    def reset(self, run_id: str) -> RunChannel:
        with self._lock:
            ch = RunChannel()
            self._channels[run_id] = ch
            return ch

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        ch = self.open(run_id)
        with ch.lock:
            ch.history.append(event)
        ch.q.put(event)

    def finish(self, run_id: str, event: dict[str, Any] | None = None) -> None:
        ch = self.open(run_id)
        if event:
            self.publish(run_id, event)
        ch.done = True
        ch.q.put({"type": "_end"})


# Module-level singleton shared by graph nodes + the API.
RUN_BUS = RunEventBus()
