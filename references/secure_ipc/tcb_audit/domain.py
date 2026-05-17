"""Домен 2: доверенный посредник аудита."""

DOMAIN_ID = "tcb_audit"
_EVENTS: list[str] = []


def append_event(parameters: dict) -> str:
    """Добавить одно событие аудита и вернуть его сообщение."""
    message = str(parameters.get("message", ""))
    _EVENTS.append(message)
    return message


def last_event(_parameters: dict) -> str:
    """Вернуть последнее добавленное событие аудита."""
    return _EVENTS[-1] if _EVENTS else ""
