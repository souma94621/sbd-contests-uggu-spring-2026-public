"""Сквозной функциональный сценарий ЦР → АБУ (основной поток миссии).

Проверяется цепочка: регистрация установки в ЦР, создание миссии, HTTP-вызов
реального приложения АБУ (без мока ответа АБУ): httpx.AsyncClient с
ASGITransport к FastAPI-приложению ``abu.app``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_e2e_dm_registers_rig_and_mission_reaches_abu(dm_client_e2e: TestClient) -> None:
    """Регистрация буровой → миссия → АБУ принимает задание и возвращает mission_id."""
    r1 = dm_client_e2e.post(
        "/api/v1/rigs",
        json={
            "rig_id": "e2e-rig-1",
            "abu_base_url": "http://127.0.0.1:8081",
            "certificate_id": None,
        },
    )
    assert r1.status_code == 200, r1.text

    r2 = dm_client_e2e.post(
        "/api/v1/missions",
        json={"rig_id": "e2e-rig-1", "target_depth_m": 12.0, "max_rpm": 180.0},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    abu_resp = body.get("abu_response") or {}
    assert abu_resp.get("accepted") is True
    assert "mission_id" in abu_resp and abu_resp["mission_id"]
