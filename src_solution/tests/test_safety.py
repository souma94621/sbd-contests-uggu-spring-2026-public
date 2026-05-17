"""Тесты проверок безопасности. Критерии: C12, C16."""

from __future__ import annotations

from src_solution.abu.tcb.limits import enforce_depth_cap, enforce_rpm_cap
from src_solution.abu.tcb.safety import should_emergency_stop


def test_depth_cap_ok():
    """Глубина в норме — продолжаем."""
    assert enforce_depth_cap(50.0, 100.0) is True


def test_depth_cap_exceeded():
    """Глубина превышена — стоп."""
    assert enforce_depth_cap(101.0, 100.0) is False


def test_rpm_cap_ok():
    """Обороты в норме — продолжаем."""
    assert enforce_rpm_cap(200.0, 300.0) is True


def test_rpm_cap_exceeded():
    """Обороты превышены — стоп."""
    assert enforce_rpm_cap(350.0, 300.0) is False


def test_emergency_stop_high_risk():
    """Высокий риск — аварийный стоп."""
    assert should_emergency_stop("high", 0.1) is True


def test_emergency_stop_low_risk():
    """Низкий риск и нормальная вибрация — нет стопа."""
    assert should_emergency_stop("low", 0.1) is False


def test_emergency_stop_high_vibration():
    """Аномальная вибрация — аварийный стоп."""
    assert should_emergency_stop("low", 0.95) is True


def test_emergency_stop_medium_risk_normal_vib():
    """Средний риск и нормальная вибрация — нет стопа."""
    assert should_emergency_stop("medium", 0.5) is False
