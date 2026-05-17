"""Процессная обёртка для одного изолированного secure IPC домена."""

from __future__ import annotations

import traceback
from multiprocessing import get_context
from multiprocessing.queues import Queue
from typing import Any, Callable


class DomainProcess:
    """Исполняет операции одного домена в выделенном процессе."""

    def __init__(
        self,
        domain_id: str,
        operations: dict[str, Callable[[dict], Any]],
    ) -> None:
        """Запустить рабочий процесс указанного домена."""
        self.domain_id = domain_id
        self._ctx = get_context("fork")
        self.requests: Queue[dict[str, Any]] = self._ctx.Queue()
        self.responses: Queue[dict[str, Any]] = self._ctx.Queue()
        self._process = self._ctx.Process(
            target=self._run,
            args=(operations, self.requests, self.responses),
            daemon=True,
        )
        self._process.start()

    def stop(self) -> None:
        """Остановить рабочий процесс."""
        self.requests.put({"command": "stop"})
        self._process.join(timeout=1)

    @staticmethod
    def _run(
        operations: dict[str, Callable[[dict], Any]],
        requests: Queue[dict[str, Any]],
        responses: Queue[dict[str, Any]],
    ) -> None:
        """Читать события из очереди запросов и публиковать ответы."""
        while True:
            message = requests.get()
            if message.get("command") == "stop":
                break
            event = message["event"]
            try:
                if event.operation not in operations:
                    raise ValueError(f"неизвестная операция {event.operation}")
                result = operations[event.operation](event.parameters)
                responses.put({
                    "request_id": message["request_id"],
                    "success": True,
                    "result": result,
                })
            except Exception:
                responses.put({
                    "request_id": message["request_id"],
                    "success": False,
                    "error": traceback.format_exc(),
                })
