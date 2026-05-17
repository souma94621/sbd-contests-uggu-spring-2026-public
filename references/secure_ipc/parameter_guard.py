"""Политики параметров операций для secure IPC событий."""

from __future__ import annotations

from collections.abc import Callable

from .ipc import Event

ParameterPolicy = Callable[[Event], bool]


class ParameterGuard:
    """Проверяет семантику полезной нагрузки после маршрутных проверок."""

    def __init__(
        self,
        policies: dict[str, ParameterPolicy] | None = None,
    ) -> None:
        """Создать проверяющий слой с параметрическими политиками."""
        self._policies = policies if policies is not None else {
            "append_event": self._check_append_event,
            "render_notice": self._check_render_notice,
            "last_event": self._check_empty_payload,
        }

    def check(self, event: Event) -> bool:
        """Вернуть True, если параметры события соответствуют политике."""
        policy = self._policies.get(event.operation)
        return bool(policy and policy(event))

    @staticmethod
    def _check_append_event(event: Event) -> bool:
        """Разрешить короткие audit-сообщения и запретить CRITICAL от UI."""
        allowed_keys = {"message", "level"}
        if set(event.parameters) - allowed_keys:
            return False
        message = event.parameters.get("message")
        if not isinstance(message, str) or not 1 <= len(message) <= 32:
            return False
        level = event.parameters.get("level", "INFO")
        if level not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
            return False
        return not (event.source == "operator_ui" and level == "CRITICAL")

    @staticmethod
    def _check_render_notice(event: Event) -> bool:
        """Разрешить отображение только коротких текстовых уведомлений."""
        allowed_keys = {"message"}
        if set(event.parameters) - allowed_keys:
            return False
        message = event.parameters.get("message")
        return isinstance(message, str) and 1 <= len(message) <= 40

    @staticmethod
    def _check_empty_payload(event: Event) -> bool:
        """Разрешить операции, которые намеренно не несут параметров."""
        return event.parameters == {}
