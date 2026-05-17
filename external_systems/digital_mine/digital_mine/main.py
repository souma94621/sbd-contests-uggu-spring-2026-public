"""REST API цифрового рудника: регистрация АБУ, выдача миссий, проверка сертификата и SGA."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel, Field

from digital_mine.sga_policy import validate_sga_payload

app = FastAPI(title="Цифровой рудник (прототип)", version="0.2.0")

_rigs: dict[str, dict[str, Any]] = {}

# Собственная цель безопасности ЦР (ЦБ)
SG_DM_AUTHORIZED_TRUSTWORTHY_OPERATORS = {
    "id": "SG_DM_Authorized_trustworthy_operators",
    "statement": (
        "При любых обстоятельствах авторизованные операторы являются благонадёжными"
    ),
}

SUPPORT_COST_FRACTION = 0.10


def _policy() -> str:
    """Режим сертификации: strict или permissive."""
    return os.environ.get("CR_CERT_POLICY", "permissive").lower()


def _regulator_url() -> str:
    """Базовый URL Регулятора."""
    return os.environ.get("REGULATOR_URL", "http://127.0.0.1:8082").rstrip("/")


async def certificate_valid(certificate_id: str) -> bool:
    """Запрос к Регулятору GET /api/v1/certificates/{id}."""
    url = f"{_regulator_url()}/api/v1/certificates/{certificate_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return False
            data = r.json()
            return bool(data.get("valid"))
    except OSError:
        return False


async def fetch_sga(certificate_id: str) -> dict[str, Any] | None:
    """SGA сертифицированной АБУ с Регулятора."""
    url = f"{_regulator_url()}/api/v1/certificates/{certificate_id}/sga"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return r.json()
    except OSError:
        return None


async def fetch_certificate_meta(certificate_id: str) -> dict[str, Any] | None:
    """Метаданные сертификата (стоимость и т.д.)."""
    url = f"{_regulator_url()}/api/v1/certificates/{certificate_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return r.json()
    except OSError:
        return None


class RigIn(BaseModel):
    """Регистрация буровой установки."""

    rig_id: str
    abu_base_url: str = Field(description="Базовый URL API АБУ, например http://127.0.0.1:8081")
    certificate_id: str | None = None


class MissionIn(BaseModel):
    """Параметры миссии для АБУ."""

    rig_id: str
    target_depth_m: float = Field(gt=0, le=200)
    max_rpm: float = Field(default=300.0, gt=0)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Проверка работоспособности ЦР."""
    return {"status": "ok", "service": "digital_mine", "policy": _policy()}


@app.get("/api/v1/security/context")
def security_context() -> dict[str, Any]:
    """ЦБ ЦР и контекст доверия к операторам."""
    return {
        "digital_mine_security_goal": SG_DM_AUTHORIZED_TRUSTWORTHY_OPERATORS,
        "policy": _policy(),
        "regulator_url": _regulator_url(),
    }


@app.get("/api/v1/rigs")
def list_rigs() -> list[dict[str, Any]]:
    """Список зарегистрированных АБУ с SGA и стоимостью поддержки."""
    out: list[dict[str, Any]] = []
    for rid, row in _rigs.items():
        out.append(
            {
                "rig_id": rid,
                "abu_base_url": row.get("abu_base_url"),
                "certificate_id": row.get("certificate_id"),
                "sga": row.get("sga"),
                "estimated_certification_cost": row.get("estimated_cost"),
                "support_cost_annual": row.get("support_cost"),
            }
        )
    return out


@app.post("/api/v1/rigs")
async def register_rig(body: RigIn) -> dict[str, Any]:
    """Зарегистрировать АБУ; при certificate_id — проверка Регулятора и SGA."""
    if body.certificate_id:
        ok = await certificate_valid(body.certificate_id)
        if not ok:
            raise HTTPException(
                status_code=403,
                detail="сертификат не подтверждён Регулятором",
            )
        sga_raw = await fetch_sga(body.certificate_id)
        if not sga_raw:
            raise HTTPException(
                status_code=403,
                detail="не удалось получить SGA с Регулятора",
            )
        payload = {
            "security_goals": sga_raw.get("security_goals", []),
            "security_assumptions": sga_raw.get("security_assumptions", []),
        }
        if not validate_sga_payload(payload):
            raise HTTPException(
                status_code=403,
                detail="SGA АБУ не соответствует политике ЦР",
            )
        meta = await fetch_certificate_meta(body.certificate_id)
        est = float((meta or {}).get("estimated_cost") or 0.0)
        support = est * SUPPORT_COST_FRACTION
        _rigs[body.rig_id] = {
            "abu_base_url": body.abu_base_url.rstrip("/"),
            "certificate_id": body.certificate_id,
            "sga": payload,
            "estimated_cost": est,
            "support_cost": support,
        }
        return {
            "registered": True,
            "rig_id": body.rig_id,
            "support_cost_annual": support,
            "sga_validated": True,
        }

    if _policy() == "strict":
        raise HTTPException(
            status_code=403,
            detail="strict: требуется certificate_id",
        )

    _rigs[body.rig_id] = {
        "abu_base_url": body.abu_base_url.rstrip("/"),
        "certificate_id": None,
        "sga": None,
        "estimated_cost": None,
        "support_cost": None,
    }
    return {"registered": True, "rig_id": body.rig_id}


@app.post("/api/v1/missions")
async def create_mission(body: MissionIn) -> dict[str, Any]:
    """Создать миссию на зарегистрированной АБУ."""
    if body.rig_id not in _rigs:
        raise HTTPException(status_code=404, detail="установка не зарегистрирована")
    rig = _rigs[body.rig_id]
    warning: str | None = None

    if _policy() == "strict":
        cid = rig.get("certificate_id")
        if not cid:
            raise HTTPException(
                status_code=403,
                detail="strict: требуется certificate_id у установки",
            )
        if not await certificate_valid(cid):
            raise HTTPException(
                status_code=403,
                detail="strict: недействительный сертификат",
            )
    else:
        if not rig.get("certificate_id"):
            warning = "permissive: работа без сертификата"

    base = rig["abu_base_url"]
    url = f"{base}/api/v1/missions"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            url,
            json={
                "target_depth_m": body.target_depth_m,
                "max_rpm": body.max_rpm,
            },
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"АБУ: {r.text}")
    out: dict[str, Any] = {"abu_response": r.json()}
    if warning:
        out["warning"] = warning
    return out
