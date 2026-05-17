"""Покрытие app.py и сценариев миссии (безопасность)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from abu.app import app


@pytest.mark.security
def test_mission_tick_flow() -> None:
    """SG: полный цикл миссии с tick и журналом."""
    c = TestClient(app)
    c.post("/api/v1/missions", json={"target_depth_m": 4.0, "max_rpm": 250.0})
    for _ in range(12):
        r = c.post("/api/v1/missions/tick")
        assert r.status_code == 200
    r_ring = c.get("/api/v1/events/ring")
    assert r_ring.status_code == 200
    assert "lines" in r_ring.json()
