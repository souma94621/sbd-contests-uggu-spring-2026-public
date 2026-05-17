"""Общий формат Event для примера secure_ipc."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    """Канонический IPC-запрос, проверяемый монитором безопасности."""

    source: str
    destination: str
    operation: str
    parameters: dict[str, Any]
