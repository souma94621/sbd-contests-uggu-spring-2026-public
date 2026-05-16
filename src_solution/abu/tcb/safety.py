"""Аварийный стоп АБУ. Доверенный компонент (ДВБ).

Намеренно не импортирует ничего из abu.other —
все входные данные передаются как примитивные типы через монитор.
"""

from __future__ import annotations

from typing import Literal

RiskLevel = Literal["low", "medium", "high"]


def should_emergency_stop(
    risk: RiskLevel,
    vibration_score: float,
    vib_threshold: float = 0.9,
) -> bool:
    """
    Аварийный стоп при высоком риске или аномальной вибрации.

    :param risk: уровень риска (строка, вычислена в other и передана через монитор)
    :param vibration_score: нормированная вибрация [0, 1]
    :param vib_threshold: порог аномалии
    :returns: True если нужна остановка
    """
    if risk == "high":
        return True
    if vibration_score >= vib_threshold:
        return True
    return False