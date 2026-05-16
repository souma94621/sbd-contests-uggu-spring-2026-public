"""HTTP API АБУ. Недоверенный компонент (other).

Все обращения к ДВБ идут через монитор безопасности.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src_solution.abu.other.ai_engine import (
    anomaly_vibration,
    regime_suggest,
    risk_flag,
    smooth_vibration_window,
)
from src_solution.abu.tcb.event_log import EventLevel
from src_solution.abu.tcb.security_monitor import enforce
from src_solution.abu.tcb.limits import enforce_depth_cap, enforce_rpm_cap
from src_solution.abu.tcb.safety import should_emergency_stop

app = FastAPI(title="АБУ (решение)", version="0.2.0")


class MissionIn(BaseModel):
    """Входное задание на бурение."""

    target_depth_m: float = Field(gt=0, le=200)
    max_rpm: float = Field(default=300.0, gt=0)


class MissionState(BaseModel):
    """Состояние текущей миссии."""

    mission_id: str
    target_depth_m: float
    depth_m: float = 0.0
    rpm: float = 0.0
    torque_nm: float = 2000.0
    pressure: float = 120.0
    vibration_samples: list[float] = Field(default_factory=list)
    status: str = "running"


_mission: MissionState | None = None


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Проверка работоспособности сервиса."""
    enforce(
        "other.app", "tcb.event_log", "record",
        lambda: __import__(
            "src_solution.abu.tcb.event_log", fromlist=["default_log"]
        ).default_log.record(EventLevel.INFO, "health_check"),
    )
    return {"status": "ok", "service": "abu"}


@app.get("/api/v1/events/ring")
def events_ring() -> dict[str, list[str]]:
    """Снимок кольцевого буфера событий."""
    from src_solution.abu.tcb.event_log import default_log
    result = enforce(
        "other.app", "tcb.event_log", "ring_snapshot",
        default_log.ring_snapshot,
    )
    return {"lines": result}


@app.get("/api/v1/events/full")
def events_full_tail() -> dict[str, str]:
    """Хвост полного журнала событий."""
    from src_solution.abu.tcb.event_log import default_log
    result = enforce(
        "other.app", "tcb.event_log", "read_full_tail",
        default_log.read_full_tail,
    )
    return {"log": result}


@app.get("/api/v1/status")
def status() -> dict[str, Any]:
    """Текущий статус и телеметрия."""
    if _mission is None:
        return {"idle": True}
    m = _mission
    vib_score = anomaly_vibration(m.vibration_samples) if m.vibration_samples else 0.0
    risk = risk_flag(vib_score, m.pressure, m.depth_m)
    return {
        "idle": False,
        "mission_id": m.mission_id,
        "depth_m": m.depth_m,
        "rpm": m.rpm,
        "torque_nm": m.torque_nm,
        "pressure": m.pressure,
        "vibration_score": vib_score,
        "risk": risk,
        "mission_status": m.status,
    }


@app.post("/api/v1/missions")
def start_mission(body: MissionIn) -> dict[str, Any]:
    """Принять новое задание."""
    global _mission
    from src_solution.abu.tcb.event_log import default_log
    mid = str(uuid.uuid4())
    _mission = MissionState(
        mission_id=mid,
        target_depth_m=body.target_depth_m,
        rpm=min(150.0, body.max_rpm),
    )
    enforce(
        "other.app", "tcb.event_log", "record",
        default_log.record,
        EventLevel.INFO,
        f"mission_started mission_id={mid} target_depth_m={body.target_depth_m}",
    )
    return {"accepted": True, "mission_id": mid}


@app.get("/api/v1/missions/current")
def current_mission() -> dict[str, Any]:
    """Текущая миссия или 404."""
    if _mission is None:
        raise HTTPException(status_code=404, detail="нет активной миссии")
    return _mission.model_dump()


@app.post("/api/v1/missions/tick")
def tick_step() -> dict[str, Any]:
    """Один шаг симуляции."""
    global _mission
    from src_solution.abu.tcb.event_log import default_log
    if _mission is None:
        raise HTTPException(status_code=400, detail="нет миссии")
    m = _mission
    if m.status != "running":
        return {"done": True, "status": m.status}

    m.depth_m = round(min(m.depth_m + 0.5, m.target_depth_m), 2)
    m.vibration_samples.append(0.1 + 0.05 * (m.depth_m % 3))
    _smooth = smooth_vibration_window(m.vibration_samples)

    enforce(
        "other.app", "tcb.event_log", "record",
        default_log.record,
        EventLevel.INFO,
        f"tick depth={m.depth_m} smooth_vib={_smooth:.4f}",
    )

    m.torque_nm = 2000 + m.depth_m * 30
    m.pressure = 120 + m.depth_m * 0.4
    rpm_suggest, _ = regime_suggest(m.depth_m, m.torque_nm)

    try:
        cap = float(os.environ.get("ABU_MAX_RPM", "300"))
    except ValueError:
        cap = 300.0
    m.rpm = min(rpm_suggest, cap)

    vib_score = anomaly_vibration(m.vibration_samples)
    risk = risk_flag(vib_score, m.pressure, m.depth_m)

    if risk == "high":
        enforce(
            "other.app", "tcb.event_log", "record",
            default_log.record,
            EventLevel.WARNING,
            f"risk_high depth_m={m.depth_m:.2f} rpm={m.rpm:.1f}",
        )

    if not enforce(
        "other.app", "tcb.limits", "enforce_depth_cap",
        enforce_depth_cap,
        m.depth_m, m.target_depth_m + 1e-6,
    ):
        m.status = "stopped_depth"
        enforce(
            "other.app", "tcb.event_log", "record",
            default_log.record,
            EventLevel.WARNING, "mission_stopped_depth_cap",
        )

    if not enforce(
        "other.app", "tcb.limits", "enforce_rpm_cap",
        enforce_rpm_cap,
        m.rpm, float(os.environ.get("ABU_MAX_RPM", "400")),
    ):
        m.status = "stopped_rpm"
        enforce(
            "other.app", "tcb.event_log", "record",
            default_log.record,
            EventLevel.ERROR, "mission_stopped_rpm_cap",
        )

    if enforce(
        "other.app", "tcb.safety", "should_emergency_stop",
        should_emergency_stop,
        risk, vib_score,
    ):
        m.status = "emergency"
        enforce(
            "other.app", "tcb.event_log", "record",
            default_log.record,
            EventLevel.CRITICAL, "emergency_stop_triggered",
        )

    if m.depth_m >= m.target_depth_m:
        m.status = "completed"
        enforce(
            "other.app", "tcb.event_log", "record",
            default_log.record,
            EventLevel.INFO, "mission_completed_target_depth",
        )

    return {"mission": m.model_dump(), "risk": risk}


class AISuggestIn(BaseModel):
    """Вход для псевдо-ИИ подсказки."""

    depth_m: float = Field(ge=0)
    torque_nm: float = Field(ge=0)


@app.post("/api/v1/ai/suggest")
def ai_suggest(body: AISuggestIn) -> dict[str, float]:
    """Псевдо-ИИ: рекомендации режима."""
    rpm, feed = regime_suggest(body.depth_m, body.torque_nm)
    return {"suggested_rpm": rpm, "suggested_feed_mm_rev": feed}