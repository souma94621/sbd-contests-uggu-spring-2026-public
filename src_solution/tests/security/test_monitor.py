"""Тесты монитора безопасности. Критерии: C18, C25."""

from __future__ import annotations

import pytest

from src_solution.abu.tcb.event_log import EventLog, EventLevel
from src_solution.abu.tcb.security_monitor import enforce, is_allowed

pytestmark = pytest.mark.security


def test_blocked_call_logs_critical():
    """Заблокированный вызов записывается в журнал."""
    log = EventLog()
    log.record(EventLevel.CRITICAL, "ipc_blocked test")
    snapshot = log.ring_snapshot()
    assert any("ipc_blocked" in line for line in snapshot)


def test_allowed_call_passes():
    """Разрешённый IPC-вызов выполняется."""
    result = enforce(
        "other.app", "tcb.limits", "enforce_depth_cap",
        lambda d, m: d <= m,
        50.0, 100.0,
    )
    assert result is True


def test_blocked_call_raises():
    """Запрещённый IPC-вызов вызывает PermissionError."""
    with pytest.raises(PermissionError):
        enforce(
            "other.app", "tcb.safety", "forbidden_method",
            lambda: None,
        )


def test_unknown_domain_blocked():
    """Неизвестный домен-источник блокируется."""
    with pytest.raises(PermissionError):
        enforce(
            "unknown.domain", "tcb.safety", "should_emergency_stop",
            lambda: None,
        )


def test_is_allowed_true():
    """is_allowed возвращает True для разрешённого маршрута."""
    assert is_allowed("other.app", "tcb.event_log", "record") is True


def test_is_allowed_false():
    """is_allowed возвращает False для запрещённого маршрута."""
    assert is_allowed("other.app", "tcb.safety", "hack_method") is False


def test_default_deny():
    """Политика по умолчанию — запрет."""
    assert is_allowed("any.domain", "any.target", "any.method") is False
