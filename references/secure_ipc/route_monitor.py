"""Маршрутный монитор с запретом по умолчанию и проверкой формы Event."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ipc import Event


def load_allows(path: Path | None = None) -> frozenset[tuple[str, str, str]]:
    """Загрузить разрешённые маршрутные тройки из JSON-политики."""
    raw_path = path or Path(__file__).with_name("ipc_policies.json")
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    return frozenset(
        (str(item["from"]), str(item["to"]), str(item["func"]))
        for item in data.get("allows", [])
    )


class RouteMonitor:
    """Точка принятия решений: запрет по умолчанию и белый список маршрутов."""

    def __init__(
        self,
        allows: frozenset[tuple[str, str, str]] | None = None,
    ) -> None:
        """Создать маршрутный монитор с явными разрешениями."""
        self._allows = allows if allows is not None else load_allows()

    def check(self, event: Any) -> bool:
        """Вернуть True для корректного Event с разрешённым маршрутом."""
        if not isinstance(event, Event):
            return False
        triple = (event.source, event.destination, event.operation)
        return triple in self._allows
