"""Локальные проверки выхода и входа доменов."""

from __future__ import annotations

from .ipc import Event

RuleSet = dict[str, frozenset[tuple[str, str]]]

DEFAULT_EGRESS: RuleSet = {
    "tcb_guard": frozenset({("tcb_audit", "append_event")}),
    "tcb_audit": frozenset({
        ("operator_ui", "render_notice"),
    }),
    "operator_ui": frozenset(),
}

DEFAULT_INGRESS: RuleSet = {
    "tcb_audit": frozenset({
        ("tcb_guard", "append_event"),
    }),
    "operator_ui": frozenset({
        ("tcb_audit", "render_notice"),
    }),
    "tcb_guard": frozenset(),
}


class DomainGuard:
    """Проверяет локальные политики отправителя и получателя."""

    def __init__(
        self,
        egress: RuleSet | None = None,
        ingress: RuleSet | None = None,
    ) -> None:
        """Создать проверяющий слой с локальными политиками."""
        self._egress = egress if egress is not None else DEFAULT_EGRESS
        self._ingress = ingress if ingress is not None else DEFAULT_INGRESS

    def check_egress(self, event: Event) -> bool:
        """Вернуть True, если отправитель может выпустить это событие."""
        allowed = self._egress.get(event.source, frozenset())
        return (event.destination, event.operation) in allowed

    def check_ingress(self, event: Event) -> bool:
        """Вернуть True, если получатель принимает это событие."""
        allowed = self._ingress.get(event.destination, frozenset())
        return (event.source, event.operation) in allowed

    def check(self, event: Event) -> bool:
        """Вернуть True, если пройдены проверки выхода и входа."""
        return self.check_egress(event) and self.check_ingress(event)
