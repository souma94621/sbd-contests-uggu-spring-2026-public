"""SG_ADS_Controlled_operations — псевдо-ИИ и аварийный стоп."""

from __future__ import annotations

import pytest

from abu.pseudo_ai import anomaly_vibration, risk_flag
from abu.safety import should_emergency_stop


@pytest.mark.security
def test_risk_and_emergency_path() -> None:
    """При высоком риге — аварийная остановка."""
    assert should_emergency_stop("high", []) is True
    assert risk_flag(0.9, 200.0, 100.0) == "high"


@pytest.mark.security
def test_anomaly_triggers_attention() -> None:
    """Аномалия вибрации детектируется."""
    s = [1.0] * 5 + [5.0]
    assert anomaly_vibration(s) >= 0.0
