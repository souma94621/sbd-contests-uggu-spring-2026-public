"""Проверки безопасности (в v1 рядом с псевдо-ИИ; на этапе 2 — в ДВБ)."""

from __future__ import annotations

from abu.pseudo_ai import RiskLevel, anomaly_vibration


def enforce_depth_cap(depth_m: float, max_depth_m: float) -> bool:
    """
    Проверка верхнего предела глубины.

    :param depth_m: текущая глубина
    :param max_depth_m: допустимый максимум
    :returns: True если можно продолжать
    """
    return depth_m <= max_depth_m


def enforce_rpm_cap(rpm: float, max_rpm: float) -> bool:
    """Проверка верхнего предела оборотов."""
    return rpm <= max_rpm


def should_emergency_stop(
    risk: RiskLevel,
    vib_samples: list[float],
    vib_threshold: float = 0.9,
) -> bool:
    """
    Аварийный стоп при высоком риске или аномальной вибрации.

    :param risk: уровень риска
    :param vib_samples: последние замеры вибрации
    :param vib_threshold: порог для anomaly_vibration
    :returns: True если нужна остановка
    """
    if risk == "high":
        return True
    if vib_samples and anomaly_vibration(vib_samples) >= vib_threshold:
        return True
    return False
