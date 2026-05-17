"""Домен 3: недоверенный интерфейс оператора."""

DOMAIN_ID = "operator_ui"


def render_notice(parameters: dict) -> str:
    """Сформировать уведомление пользователя из разрешённого IPC-события."""
    return f"notice: {parameters.get('message', '')}"
