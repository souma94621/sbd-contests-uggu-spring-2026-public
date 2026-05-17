"""Проверки лимитов АБУ. Доверенный компонент (ДВБ)."""

from __future__ import annotations


def enforce_depth_cap(depth_m: float, max_depth_m: float) -> bool:
    """
    Проверка верхнего предела глубины.

    :param depth_m: текущая глубина
    :param max_depth_m: допустимый максимум
    :returns: True если можно продолжать
    """
    return depth_m <= max_depth_m


def enforce_rpm_cap(rpm: float, max_rpm: float) -> bool:
    """
    Проверка верхнего предела оборотов.

    :param rpm: текущие обороты
    :param max_rpm: допустимый максимум
    :returns: True если можно продолжать
    """
    return rpm <= max_rpm
