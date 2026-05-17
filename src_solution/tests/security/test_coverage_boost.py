"""Дополнительные security-тесты для повышения coverage до ≥70%.

Файл: src_solution/tests/security/test_coverage_boost.py
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


import src_solution.abu.other.app as _app_module

pytestmark = pytest.mark.security


# ────────────────────────────────────────────────
# safety.py
# ────────────────────────────────────────────────

class TestShouldEmergencyStop:
    def test_high_risk_triggers_stop(self):
        """risk=high всегда вызывает остановку."""
        from src_solution.abu.tcb.safety import should_emergency_stop
        assert should_emergency_stop("high", 0.0) is True

    def test_low_risk_no_stop(self):
        """risk=low и низкая вибрация — нет остановки."""
        from src_solution.abu.tcb.safety import should_emergency_stop
        assert should_emergency_stop("low", 0.1) is False

    def test_medium_risk_no_stop(self):
        """risk=medium и вибрация ниже порога — нет остановки."""
        from src_solution.abu.tcb.safety import should_emergency_stop
        assert should_emergency_stop("medium", 0.5) is False

    def test_vib_at_threshold_triggers_stop(self):
        """Вибрация ровно на пороге 0.9 — остановка."""
        from src_solution.abu.tcb.safety import should_emergency_stop
        assert should_emergency_stop("low", 0.9) is True

    def test_vib_above_threshold_triggers_stop(self):
        """Вибрация выше порога — остановка."""
        from src_solution.abu.tcb.safety import should_emergency_stop
        assert should_emergency_stop("medium", 0.95) is True

    def test_vib_just_below_threshold_no_stop(self):
        """Вибрация чуть ниже порога — нет остановки."""
        from src_solution.abu.tcb.safety import should_emergency_stop
        assert should_emergency_stop("low", 0.89) is False

    def test_custom_threshold(self):
        """Кастомный порог вибрации работает корректно."""
        from src_solution.abu.tcb.safety import should_emergency_stop
        assert should_emergency_stop("low", 0.5, vib_threshold=0.4) is True
        assert should_emergency_stop("low", 0.3, vib_threshold=0.4) is False


# ────────────────────────────────────────────────
# limits.py
# ────────────────────────────────────────────────

class TestEnforceDepthCap:
    def test_within_limit(self):
        from src_solution.abu.tcb.limits import enforce_depth_cap
        assert enforce_depth_cap(50.0, 100.0) is True

    def test_at_limit(self):
        from src_solution.abu.tcb.limits import enforce_depth_cap
        assert enforce_depth_cap(100.0, 100.0) is True

    def test_over_limit(self):
        from src_solution.abu.tcb.limits import enforce_depth_cap
        assert enforce_depth_cap(100.1, 100.0) is False

    def test_zero_depth(self):
        from src_solution.abu.tcb.limits import enforce_depth_cap
        assert enforce_depth_cap(0.0, 100.0) is True


class TestEnforceRpmCap:
    def test_within_limit(self):
        from src_solution.abu.tcb.limits import enforce_rpm_cap
        assert enforce_rpm_cap(200.0, 300.0) is True

    def test_at_limit(self):
        from src_solution.abu.tcb.limits import enforce_rpm_cap
        assert enforce_rpm_cap(300.0, 300.0) is True

    def test_over_limit(self):
        from src_solution.abu.tcb.limits import enforce_rpm_cap
        assert enforce_rpm_cap(300.1, 300.0) is False

    def test_zero_rpm(self):
        from src_solution.abu.tcb.limits import enforce_rpm_cap
        assert enforce_rpm_cap(0.0, 300.0) is True


# ────────────────────────────────────────────────
# ai_engine.py
# ────────────────────────────────────────────────

class TestAnomalyVibration:
    def test_empty_returns_one(self):
        from src_solution.abu.other.ai_engine import anomaly_vibration
        assert anomaly_vibration([]) == 1.0

    def test_single_sample_returns_zero(self):
        from src_solution.abu.other.ai_engine import anomaly_vibration
        assert anomaly_vibration([0.5]) == 0.0

    def test_stable_samples_low_anomaly(self):
        from src_solution.abu.other.ai_engine import anomaly_vibration
        result = anomaly_vibration([0.1, 0.1, 0.1, 0.1, 0.1])
        assert result == 0.0

    def test_spike_gives_high_anomaly(self):
        from src_solution.abu.other.ai_engine import anomaly_vibration
        result = anomaly_vibration([0.1, 0.1, 0.1, 0.1, 0.9])
        assert result > 0.5

    def test_result_in_range(self):
        from src_solution.abu.other.ai_engine import anomaly_vibration
        result = anomaly_vibration([0.2, 0.5, 0.1, 0.8, 0.3])
        assert 0.0 <= result <= 1.0


class TestSmoothVibrationWindow:
    def test_empty_returns_zero(self):
        from src_solution.abu.other.ai_engine import smooth_vibration_window
        assert smooth_vibration_window([]) == 0.0

    def test_single_sample(self):
        from src_solution.abu.other.ai_engine import smooth_vibration_window
        assert smooth_vibration_window([0.4]) == pytest.approx(0.4)

    def test_averages_window(self):
        from src_solution.abu.other.ai_engine import smooth_vibration_window
        result = smooth_vibration_window([0.2, 0.4, 0.6])
        assert result == pytest.approx(0.4)

    def test_uses_last_n(self):
        from src_solution.abu.other.ai_engine import smooth_vibration_window
        result = smooth_vibration_window([99.0] * 10 + [1.0, 1.0, 1.0, 1.0, 1.0])
        assert result == pytest.approx(1.0)


class TestRegimeSuggest:
    def test_returns_tuple(self):
        from src_solution.abu.other.ai_engine import regime_suggest
        rpm, feed = regime_suggest(50.0, 2000.0)
        assert isinstance(rpm, float)
        assert isinstance(feed, float)

    def test_high_torque_reduces_rpm(self):
        from src_solution.abu.other.ai_engine import regime_suggest
        rpm_normal, _ = regime_suggest(50.0, 2000.0)
        rpm_high, _ = regime_suggest(50.0, 6000.0)
        assert rpm_high < rpm_normal

    def test_deep_increases_rpm(self):
        from src_solution.abu.other.ai_engine import regime_suggest
        rpm_shallow, _ = regime_suggest(10.0, 2000.0)
        rpm_deep, _ = regime_suggest(80.0, 2000.0)
        assert rpm_deep > rpm_shallow

    def test_feed_grows_with_depth(self):
        from src_solution.abu.other.ai_engine import regime_suggest
        _, feed_shallow = regime_suggest(5.0, 2000.0)
        _, feed_deep = regime_suggest(50.0, 2000.0)
        assert feed_deep > feed_shallow


class TestRiskFlag:
    def test_low_risk_all_normal(self):
        from src_solution.abu.other.ai_engine import risk_flag
        assert risk_flag(0.1, 100.0, 10.0) == "low"

    def test_medium_risk_slight_vibration(self):
        from src_solution.abu.other.ai_engine import risk_flag
        assert risk_flag(0.8, 100.0, 10.0) == "medium"

    def test_high_risk_all_bad(self):
        from src_solution.abu.other.ai_engine import risk_flag
        assert risk_flag(0.9, 200.0, 100.0) == "high"

    def test_high_pressure_alone_gives_medium(self):
        from src_solution.abu.other.ai_engine import risk_flag
        assert risk_flag(0.0, 190.0, 10.0) == "medium"

    def test_deep_depth_alone_gives_medium(self):
        from src_solution.abu.other.ai_engine import risk_flag
        assert risk_flag(0.0, 100.0, 96.0) == "medium"

    def test_high_vib_and_pressure_gives_high(self):
        from src_solution.abu.other.ai_engine import risk_flag
        assert risk_flag(0.8, 190.0, 10.0) == "high"


# ────────────────────────────────────────────────
# security_monitor.py — дополнительные ветки
# ────────────────────────────────────────────────

class TestSecurityMonitorExtra:
    def test_enforce_calls_function_with_args(self):
        """enforce передаёт аргументы в функцию корректно."""
        from src_solution.abu.tcb.security_monitor import enforce
        result = enforce(
            "other.app", "tcb.limits", "enforce_depth_cap",
            lambda a, b: a + b,
            10.0, 5.0,
        )
        assert result == 15.0

    def test_enforce_blocked_does_not_call_func(self):
        """Заблокированный вызов не выполняет функцию."""
        called = []
        from src_solution.abu.tcb.security_monitor import enforce
        with pytest.raises(PermissionError):
            enforce(
                "other.app", "tcb.safety", "nonexistent",
                lambda: called.append(True),
            )
        assert called == []

    def test_is_allowed_known_good_routes(self):
        """Проверка всех ожидаемо разрешённых маршрутов."""
        from src_solution.abu.tcb.security_monitor import is_allowed
        allowed_routes = [
            ("other.app", "tcb.limits", "enforce_depth_cap"),
            ("other.app", "tcb.limits", "enforce_rpm_cap"),
            ("other.app", "tcb.event_log", "record"),
            ("other.app", "tcb.event_log", "ring_snapshot"),
            ("other.app", "tcb.safety", "should_emergency_stop"),
        ]
        for from_d, to_d, method in allowed_routes:
            assert is_allowed(from_d, to_d, method) is True, (
                f"Маршрут должен быть разрешён: {from_d} -> {to_d}.{method}"
            )

    def test_is_allowed_without_deny_default(self, monkeypatch):
        """Если default != deny — всё разрешено (строка 48)."""
        from src_solution.abu.tcb import security_monitor
        monkeypatch.setattr(
            security_monitor, "_load_policies",
            lambda: {"default": "allow", "allows": []},
        )
        assert security_monitor.is_allowed("any.domain", "any.target", "any_method") is True


# ────────────────────────────────────────────────
# event_log.py — непокрытые ветки
# ────────────────────────────────────────────────

class TestEventLogMissingBranches:
    def test_record_all_levels(self, tmp_path):
        """Запись всех уровней событий (строки 35-36)."""
        from src_solution.abu.tcb.event_log import EventLog, EventLevel
        log = EventLog(log_dir=tmp_path)
        for level in EventLevel:
            log.record(level, f"test_{level.value}")
        snap = log.ring_snapshot()
        assert len(snap) > 0

    def test_record_oserror_on_write(self, tmp_path):
        """OSError при записи файла не роняет процесс (строки 55-56)."""
        from src_solution.abu.tcb.event_log import EventLog, EventLevel
        log = EventLog(log_dir=tmp_path)
        log._full_path.mkdir(parents=True, exist_ok=True)
        log.record(EventLevel.ERROR, "should_not_crash")

    def test_read_full_tail_file_not_exists(self, tmp_path):
        """read_full_tail возвращает '' если файла нет (строка 65)."""
        from src_solution.abu.tcb.event_log import EventLog
        log = EventLog(log_dir=tmp_path / "empty")
        assert log.read_full_tail() == ""

    def test_read_full_tail_with_max_lines(self, tmp_path):
        """read_full_tail обрезает до max_lines (строки 66-68)."""
        from src_solution.abu.tcb.event_log import EventLog, EventLevel
        log = EventLog(log_dir=tmp_path)
        for i in range(20):
            log.record(EventLevel.INFO, f"msg_{i}")
        result = log.read_full_tail(max_lines=5)
        lines = result.splitlines()
        assert len(lines) == 5
        assert "msg_19" in result


# ────────────────────────────────────────────────
# app.py — покрытие через FastAPI TestClient
# ────────────────────────────────────────────────


@pytest.fixture()
def client():
    _app_module._mission = None
    yield TestClient(_app_module.app)
    _app_module._mission = None


def test_app_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_app_events_ring(client):
    resp = client.get("/api/v1/events/ring")
    assert resp.status_code == 200
    assert "lines" in resp.json()


def test_app_events_full(client):
    resp = client.get("/api/v1/events/full")
    assert resp.status_code == 200
    assert "log" in resp.json()


def test_app_status_idle(client):
    resp = client.get("/api/v1/status")
    assert resp.json()["idle"] is True


def test_app_start_mission(client):
    resp = client.post("/api/v1/missions", json={"target_depth_m": 10.0})
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


def test_app_start_mission_invalid_zero(client):
    resp = client.post("/api/v1/missions", json={"target_depth_m": 0.0})
    assert resp.status_code == 422


def test_app_start_mission_invalid_too_deep(client):
    resp = client.post("/api/v1/missions", json={"target_depth_m": 201.0})
    assert resp.status_code == 422


def test_app_current_mission_404(client):
    resp = client.get("/api/v1/missions/current")
    assert resp.status_code == 404


def test_app_current_mission_ok(client):
    client.post("/api/v1/missions", json={"target_depth_m": 10.0})
    resp = client.get("/api/v1/missions/current")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_app_tick_no_mission(client):
    resp = client.post("/api/v1/missions/tick")
    assert resp.status_code == 400


def test_app_tick_advances_depth(client):
    client.post("/api/v1/missions", json={"target_depth_m": 50.0})
    resp = client.post("/api/v1/missions/tick")
    assert resp.status_code == 200
    assert resp.json()["mission"]["depth_m"] > 0.0


def test_app_tick_returns_risk(client):
    client.post("/api/v1/missions", json={"target_depth_m": 50.0})
    resp = client.post("/api/v1/missions/tick")
    assert resp.json()["risk"] in ("low", "medium", "high")


def test_app_tick_until_completed(client):
    """Миссия завершается по достижении целевой глубины."""
    client.post("/api/v1/missions", json={"target_depth_m": 1.0})
    for _ in range(10):
        r = client.post("/api/v1/missions/tick")
        if r.json()["mission"]["status"] != "running":
            break
    assert r.json()["mission"]["status"] == "completed"


def test_app_tick_after_completed_returns_done(client):
    """Тик после завершения возвращает done=True."""
    client.post("/api/v1/missions", json={"target_depth_m": 1.0})
    for _ in range(10):
        client.post("/api/v1/missions/tick")
    resp = client.post("/api/v1/missions/tick")
    assert resp.json().get("done") is True


def test_app_status_with_mission(client):
    client.post("/api/v1/missions", json={"target_depth_m": 50.0})
    client.post("/api/v1/missions/tick")
    resp = client.get("/api/v1/status")
    data = resp.json()
    assert data["idle"] is False
    assert "risk" in data
    assert "depth_m" in data


def test_app_ai_suggest(client):
    resp = client.post("/api/v1/ai/suggest", json={"depth_m": 30.0, "torque_nm": 2000.0})
    assert resp.status_code == 200
    assert "suggested_rpm" in resp.json()
    assert "suggested_feed_mm_rev" in resp.json()
