"""Домен 1: доверенный guard."""

DOMAIN_ID = "tcb_guard"


def approve(parameters: dict) -> bool:
    """Вернуть малое доверенное решение для демонстрации."""
    return bool(parameters.get("ok", False))
