"""Тесты псевдо-ИИ модулей."""

import pytest

from abu.pseudo_ai import anomaly_vibration, regime_suggest, risk_flag


def test_anomaly_single_sample() -> None:
    """Один замер даёт нулевую аномалию относительно окна."""
    assert anomaly_vibration([1.0]) == 0.0


def test_anomaly_spike() -> None:
    """Всплеск увеличивает score."""
    samples = [1.0, 1.0, 1.0, 1.0, 1.0, 3.0]
    assert anomaly_vibration(samples) > 0.5


def test_regime_suggest_depth() -> None:
    """Глубина увеличивает базовые обороты."""
    r1, f1 = regime_suggest(0.0, 1000.0)
    r2, f2 = regime_suggest(10.0, 1000.0)
    assert r2 >= r1
    assert f2 >= f1


def test_regime_high_torque_reduces_rpm() -> None:
    """Высокий момент снижает обороты."""
    r_low, _ = regime_suggest(10.0, 1000.0)
    r_high, _ = regime_suggest(10.0, 6000.0)
    assert r_high <= r_low


@pytest.mark.parametrize(
    "vib,press,depth,expected",
    [
        (0.1, 100.0, 10.0, "low"),
        (0.8, 100.0, 10.0, "medium"),
        (0.9, 200.0, 100.0, "high"),
    ],
)
def test_risk_flag(
    vib: float,
    press: float,
    depth: float,
    expected: str,
) -> None:
    """Уровни риска по порогам."""
    assert risk_flag(vib, press, depth) == expected
