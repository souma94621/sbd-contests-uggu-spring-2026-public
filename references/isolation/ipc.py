"""Минимальный очередной IPC для изолированных доменов безопасности."""

from __future__ import annotations

import traceback
import uuid
from dataclasses import dataclass
from multiprocessing import get_context
from multiprocessing.queues import Queue
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    """Канонический запрос между изолированными доменами."""

    source: str
    destination: str
    operation: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Result:
    """Асинхронный результат, который публикует рабочий процесс домена."""

    request_id: str
    success: bool
    result: Any = None
    error: str = ""


class DomainProcess:
    """Запускает операции одного домена в отдельном процессе."""

    def __init__(
        self,
        domain_id: str,
        operations: dict[str, Callable[[dict], Any]],
    ) -> None:
        """Запустить процесс домена с заданной картой операций."""
        self.domain_id = domain_id
        self._ctx = get_context("fork")
        self.inbox: Queue[dict[str, Any]] = self._ctx.Queue()
        self.outbox: Queue[Result] = self._ctx.Queue()
        self._process = self._ctx.Process(
            target=self._run,
            args=(operations, self.inbox, self.outbox),
            daemon=True,
        )
        self._process.start()

    def send(self, event: Event) -> str:
        """Отправить событие без ожидания результата."""
        request_id = uuid.uuid4().hex
        self.inbox.put({"request_id": request_id, "event": event})
        return request_id

    def receive(self, request_id: str, timeout: float = 2.0) -> Any:
        """Получить результат ранее отправленного события."""
        result = self.outbox.get(timeout=timeout)
        if result.request_id != request_id:
            raise RuntimeError(
                f"неожиданный id результата {result.request_id}",
            )
        if not result.success:
            raise RuntimeError(result.error)
        return result.result

    def stop(self) -> None:
        """Остановить рабочий процесс домена."""
        self.inbox.put({"command": "stop"})
        self._process.join(timeout=1)

    @staticmethod
    def _run(
        operations: dict[str, Callable[[dict], Any]],
        inbox: Queue[dict[str, Any]],
        outbox: Queue[Result],
    ) -> None:
        """Обрабатывать входящие события из inbox до команды остановки."""
        while True:
            message = inbox.get()
            if message.get("command") == "stop":
                break
            event = message["event"]
            try:
                if event.operation not in operations:
                    raise ValueError(f"неизвестная операция {event.operation}")
                result = operations[event.operation](event.parameters)
                outbox.put(Result(message["request_id"], True, result))
            except Exception:
                outbox.put(
                    Result(
                        request_id=message["request_id"],
                        success=False,
                        error=traceback.format_exc(),
                    ),
                )
