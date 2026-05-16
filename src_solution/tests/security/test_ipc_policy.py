"""Тесты IPC-политик. Критерии: C24, C25."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src_solution.abu.tcb.security_monitor import is_allowed

pytestmark = pytest.mark.security

_POLICIES_PATH = (
    Path(__file__).parent.parent.parent / "abu" / "tcb" / "ipc_policies.json"
)


def test_policies_file_exists():
    """Файл политик существует."""
    assert _POLICIES_PATH.is_file()


def test_policies_valid_json():
    """Файл политик — валидный JSON."""
    data = json.loads(_POLICIES_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_default_is_deny():
    """Политика по умолчанию — deny."""
    data = json.loads(_POLICIES_PATH.read_text(encoding="utf-8"))
    assert data.get("default") == "deny"


def test_allows_list_exists():
    """Список разрешений существует."""
    data = json.loads(_POLICIES_PATH.read_text(encoding="utf-8"))
    assert "allows" in data
    assert isinstance(data["allows"], list)


def test_no_wildcard_rules():
    """Нет правил с wildcard — каждое правило явное."""
    data = json.loads(_POLICIES_PATH.read_text(encoding="utf-8"))
    for rule in data["allows"]:
        assert "*" not in rule["from"]
        assert "*" not in rule["to"]
        assert "*" not in rule["method"]


def test_tcb_cannot_call_other():
    """ДВБ не может вызывать недоверенный код."""
    assert is_allowed("tcb.safety", "other.app", "any_method") is False
    assert is_allowed("tcb.event_log", "other.ai_engine", "risk_flag") is False