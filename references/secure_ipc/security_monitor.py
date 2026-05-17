"""Совместимый фасад для маршрутных проверок безопасности."""

from __future__ import annotations

from .ipc import Event
from .route_monitor import RouteMonitor


class SecurityMonitor(RouteMonitor):
    """Обратно совместимое имя для маршрутного монитора."""

    def __init__(
        self,
        allows: frozenset[tuple[str, str, str]] | None = None,
    ) -> None:
        """Создать монитор с явными разрешающими тройками."""
        super().__init__(allows)

    def check(self, event: Event) -> bool:
        """Вернуть True только для разрешённых маршрутов Event."""
        return super().check(event)
