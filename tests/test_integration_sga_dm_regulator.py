"""Интеграция ЦР ↔ Регулятор: SGA по сертификату."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def dm_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """ЦР с подменой HTTP к Регулятору."""
    monkeypatch.setenv("CR_CERT_POLICY", "strict")

    class Resp:
        def __init__(self, status: int, data: dict | None = None):
            self.status_code = status
            self._data = data or {}

        def json(self):
            return self._data

    class AC:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *x):
            return None

        async def get(self, url: str):
            if "/certificates/c1/sga" in url:
                return Resp(
                    200,
                    {
                        "certificate_id": "c1",
                        "security_goals": [
                            {"id": "SG_ADS_Authorized_critical_commands", "statement": "a"},
                            {"id": "SG_ADS_Controlled_operations", "statement": "b"},
                            {"id": "SG_ADS_Security_events_store", "statement": "c"},
                        ],
                        "security_assumptions": [
                            {
                                "id": "SA_ADS_Trustrworthy_authorized_operators",
                                "statement": "d",
                            }
                        ],
                    },
                )
            if "/certificates/c1" in url and "/sga" not in url:
                return Resp(200, {"valid": True, "estimated_cost": 5000.0})
            return Resp(404)

        async def post(self, url: str, **kw):
            return Resp(200, {"accepted": True})

    import digital_mine.main as dm

    monkeypatch.setattr(dm.httpx, "AsyncClient", AC)
    return TestClient(dm.app)


def test_register_rig_with_cert_requires_sga_ok(dm_client: TestClient) -> None:
    """Регистрация с certificate_id при успешном SGA."""
    r = dm_client.post(
        "/api/v1/rigs",
        json={
            "rig_id": "r1",
            "abu_base_url": "http://127.0.0.1:8081",
            "certificate_id": "c1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("sga_validated") is True
    assert body.get("support_cost_annual") == pytest.approx(500.0)


def test_security_context_has_dm_sg() -> None:
    """ЦБ ЦР отдаётся в контексте."""
    from digital_mine.main import app

    c = TestClient(app)
    r = c.get("/api/v1/security/context")
    assert r.status_code == 200
    js = r.json()
    assert js["digital_mine_security_goal"]["id"] == "SG_DM_Authorized_trustworthy_operators"
