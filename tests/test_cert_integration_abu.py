"""Автотест полного цикла сертификации пакета src_starting_point."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bundle_path() -> Path:
    """Собирает сертификационный пакет через тот же скрипт, что и make."""
    subprocess.run(
        ["bash", str(ROOT / "scripts" / "prepare_certification_bundle.sh")],
        cwd=ROOT,
        check=True,
    )
    p = ROOT / "artifacts" / "abu_certification_bundle.tar.gz"
    assert p.is_file()
    return p


def test_certification_success_and_certificate_is_sha256_of_bundle(
    bundle_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /certification/requests возвращает success, cost и certificate_id = SHA-256 архива."""
    monkeypatch.setenv("REGULATOR_COV_FAIL_UNDER", "60")
    monkeypatch.setenv("REGULATOR_SECURITY_COV_FAIL_UNDER", "60")
    from regulator.main import app

    expected = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    client = TestClient(app)
    r = client.post(
        "/api/v1/certification/requests",
        json={
            "bundle_path": str(bundle_path.resolve()),
            "developer_company": "Локальный тест",
            "firmware_label": "abu-sp",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    assert body.get("certificate_id") == expected
    assert float(body.get("estimated_cost", 0)) > 0
    assert float(body.get("coverage_tcb_percent", 0)) >= 40.0
    assert body.get("developer_company") == "Локальный тест"
    assert body.get("firmware_label") == "abu-sp"


def test_certificate_lookup(bundle_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /certificates/{id} после успешной сертификации."""
    monkeypatch.setenv("REGULATOR_COV_FAIL_UNDER", "60")
    monkeypatch.setenv("REGULATOR_SECURITY_COV_FAIL_UNDER", "60")
    from regulator.main import app

    client = TestClient(app)
    r = client.post(
        "/api/v1/certification/requests",
        json={
            "bundle_path": str(bundle_path.resolve()),
            "developer_company": "Локальный тест",
        },
    )
    cid = r.json()["certificate_id"]
    g = client.get(f"/api/v1/certificates/{cid}")
    assert g.status_code == 200
    assert g.json().get("valid") is True
    sg = client.get(f"/api/v1/certificates/{cid}/sga")
    assert sg.status_code == 200
    assert len(sg.json().get("security_goals", [])) >= 3
