"""Интеграционные проверки ЦР без реального АБУ (мок httpx)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class MockAsyncClient:
    """Имитация httpx.AsyncClient для АБУ и Регулятора."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        class R:
            status_code = 200
            text = ""

            def json(self):
                return {"accepted": True, "mission_id": "test-mission"}

        return R()

    async def get(self, url):
        class R:
            status_code = 200

            def json(self):
                return {"valid": True}

        return R()


@pytest.fixture()
def dm_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient для ЦР с подменой внешних HTTP-вызовов."""
    monkeypatch.setenv("CR_CERT_POLICY", "permissive")
    import digital_mine.main as dm

    monkeypatch.setattr(dm.httpx, "AsyncClient", MockAsyncClient)
    return TestClient(dm.app)


def test_health(dm_client: TestClient) -> None:
    """GET /api/v1/health."""
    r = dm_client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_mission_permissive_without_certificate(dm_client: TestClient) -> None:
    """В permissive миссия проходит без сертификата (с предупреждением)."""
    r1 = dm_client.post(
        "/api/v1/rigs",
        json={
            "rig_id": "rig-1",
            "abu_base_url": "http://127.0.0.1:9999",
            "certificate_id": None,
        },
    )
    assert r1.status_code == 200
    r2 = dm_client.post(
        "/api/v1/missions",
        json={"rig_id": "rig-1", "target_depth_m": 10.0, "max_rpm": 200.0},
    )
    assert r2.status_code == 200
    assert "warning" in r2.json()
