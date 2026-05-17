"""Монитор безопасности АБУ. Доверенный компонент (ДВБ).

Реализует шаблон А.2 ГОСТ Р 72118-2025
«Раздельное принятие и применение решений о безопасности»:
  - decision point: проверяет ipc_policies.json
  - enforcement point: разрешает или блокирует IPC-вызов
  - default deny: всё запрещено, если нет явного разрешения
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src_solution.abu.tcb.event_log import EventLevel, default_log

_POLICIES_PATH = Path(__file__).parent / "ipc_policies.json"


def _load_policies() -> dict:
    """Загрузить политики из файла."""
    with _POLICIES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def is_allowed(from_domain: str, to_domain: str, method: str) -> bool:
    """
    Decision point: проверить разрешён ли вызов по политикам.

    :param from_domain: домен-источник (например 'other.app')
    :param to_domain: домен-получатель (например 'tcb.safety')
    :param method: имя метода
    :returns: True если вызов разрешён
    """
    policies = _load_policies()

    if policies.get("default") == "deny":
        for rule in policies.get("allows", []):
            if (
                rule["from"] == from_domain
                and rule["to"] == to_domain
                and rule["method"] == method
            ):
                return True
        return False

    return True


def enforce(
    from_domain: str,
    to_domain: str,
    method: str,
    func: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Enforcement point: выполнить вызов если разрешён, иначе заблокировать.

    :param from_domain: домен-источник
    :param to_domain: домен-получатель
    :param method: имя метода
    :param func: функция для вызова
    :param args: позиционные аргументы
    :param kwargs: именованные аргументы
    :returns: результат вызова
    :raises PermissionError: если вызов запрещён политикой
    """
    if is_allowed(from_domain, to_domain, method):
        default_log.record(
            EventLevel.INFO,
            f"ipc_allowed from={from_domain} to={to_domain} method={method}",
        )
        return func(*args, **kwargs)

    default_log.record(
        EventLevel.CRITICAL,
        f"ipc_blocked from={from_domain} to={to_domain} method={method}",
    )
    raise PermissionError(
        f"IPC запрещён политикой: {from_domain} -> {to_domain}.{method}"
    )
