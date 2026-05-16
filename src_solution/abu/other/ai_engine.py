"""Псевдо-ИИ и обработка вибрации. Недоверенный компонент (other).

numpy используется здесь намеренно — он должен быть только в SBOM_OTHER.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

RiskLevel = Literal["low", "medium", "high"]


def anomaly_vibration(samples: list[float]) -> float:
    """
    Оценка аномальности вибрации.

    :param samples: ряд замеров (не пустой)
    :returns: значение в диапазоне [0, 1]
    """
    if not samples:
        return 1.0
    if len(samples) == 1:
        return 0.0
    window = samples[-5:]
    mean = sum(window) / len(window)
    last = window[-1]
    spread = max(abs(x - mean) for x in window) or 1e-9
    raw = abs(last - mean) / spread
    return max(0.0, min(1.0, raw))


def smooth_vibration_window(samples: list[float], window: int = 5) -> float:
    """
    Сглаживание ряда вибраций скользящим средним через numpy.

    :param samples: замеры
    :param window: размер окна
    :returns: сглаженное значение по последнему окну
    """
    if not samples:
        return 0.0
    arr = np.array(samples[-window:], dtype=np.float64)
    return float(np.mean(arr))


def regime_suggest(depth_m: float, torque_nm: float) -> tuple[float, float]:
    """
    Эвристика рекомендуемых оборотов и подачи.

    :param depth_m: текущая глубина, м
    :param torque_nm: крутящий момент, Н·м
    :returns: (обороты_об_мин, подача_мм_об)
    """
    rpm = 120.0 + min(depth_m * 2.0, 80.0)
    if torque_nm > 5000:
        rpm *= 0.85
    feed = 0.2 + min(depth_m * 0.01, 0.15)
    return round(rpm, 1), round(feed, 3)


def risk_flag(vibration: float, pressure: float, depth_m: float) -> RiskLevel:
    """
    Пороговый классификатор риска по сенсорам.

    :param vibration: нормированная вибрация [0, 1]
    :param pressure: давление, усл. ед.
    :param depth_m: глубина, м
    :returns: уровень риска
    """
    score = 0
    if vibration > 0.75:
        score += 2
    if pressure > 180.0:
        score += 2
    if depth_m > 95.0:
        score += 1
    if score >= 3:
        return "high"
    if score >= 1:
        return "medium"
    return "low"