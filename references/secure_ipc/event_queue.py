"""Очередь событий монитора для примера secure_ipc."""

from __future__ import annotations

from multiprocessing import get_context
from multiprocessing.queues import Queue
from typing import Any


class MonitorEventQueue:
    """Очередь, принимающая все IPC-события до проверки политик."""

    def __init__(self) -> None:
        """Создать центральную очередь монитора."""
        self._ctx = get_context("fork")
        self._queue: Queue[Any] = self._ctx.Queue()

    def put(self, event: Any) -> None:
        """Положить объект события в очередь монитора."""
        self._queue.put(event)

    def get(self) -> Any:
        """Прочитать следующее ожидающее событие из очереди монитора."""
        return self._queue.get(timeout=2)
