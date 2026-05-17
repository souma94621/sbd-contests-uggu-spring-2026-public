"""Брокер сообщений, доставляющий только авторизованные события."""

from __future__ import annotations

import uuid
from typing import Any

from .domain_guard import DomainGuard
from .domain_process import DomainProcess
from .event_queue import MonitorEventQueue
from .ipc import Event
from .parameter_guard import ParameterGuard
from .route_monitor import RouteMonitor


class MessageBroker:
    """Маршрутизирует события через все слои проверок политик."""

    def __init__(
        self,
        route_monitor: RouteMonitor | None = None,
        domain_guard: DomainGuard | None = None,
        parameter_guard: ParameterGuard | None = None,
        event_queue: MonitorEventQueue | None = None,
    ) -> None:
        """Создать брокер с маршрутным, доменным и параметрическим слоем."""
        self._route_monitor = route_monitor or RouteMonitor()
        self._domain_guard = domain_guard or DomainGuard()
        self._parameter_guard = parameter_guard or ParameterGuard()
        self._event_queue = event_queue or MonitorEventQueue()
        self._domains: dict[str, DomainProcess] = {}

    def register(self, domain: DomainProcess) -> None:
        """Зарегистрировать процесс домена по его идентификатору."""
        self._domains[domain.domain_id] = domain

    def send(self, event: Event) -> Any:
        """Положить событие в очередь монитора и доставить после проверок."""
        self._event_queue.put(event)
        queued_event = self._event_queue.get()
        if not self._route_monitor.check(queued_event):
            raise PermissionError(
                f"запрещено маршрутной политикой: {queued_event}",
            )
        if not self._domain_guard.check(queued_event):
            raise PermissionError(
                f"запрещено доменной политикой: {queued_event}",
            )
        if not self._parameter_guard.check(queued_event):
            raise PermissionError(
                f"запрещено политикой параметров: {queued_event}",
            )
        target = self._domains[queued_event.destination]
        request_id = uuid.uuid4().hex
        target.requests.put({"request_id": request_id, "event": queued_event})
        response = target.responses.get(timeout=2)
        if not response["success"]:
            raise RuntimeError(response["error"])
        return response["result"]
