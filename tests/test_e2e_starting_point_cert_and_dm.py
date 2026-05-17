"""Сквозной сценарий для заготовки: сертификация (высокая стоимость, numpy в TCB) + ЦР → АБУ."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regulator.cost_model import (
    HEAVY_DEP_COST_MULTIPLIER,
    apply_heavy_dep_multiplier,
    sbom_has_heavy_dep,
    total_estimated_cost,
)
from regulator.sbom_parse import count_sbom_metrics
from regulator.tcb_metrics import compute_tcb_source_metrics

ROOT = Path(__file__).resolve().parents[1]

# Нижняя граница «завышенной» оценки для текущей модели и дерева src_starting_point
# (полный abu как TCB + SBOM с рёбрами + множитель numpy). Подобрано с запасом под CI.
STARTING_POINT_MIN_CERT_COST = 1500.0


@pytest.fixture(scope="module")
def bundle_path() -> Path:
    """Собирает сертификационный пакет так же, как make prepare-cert-bundle."""
    subprocess.run(
        ["bash", str(ROOT / "scripts" / "prepare_certification_bundle.sh")],
        cwd=ROOT,
        check=True,
    )
    p = ROOT / "artifacts" / "abu_certification_bundle.tar.gz"
    assert p.is_file()
    return p


@pytest.fixture(scope="module")
def cert_bundle_dir(bundle_path: Path) -> Path:
    """Распакованный каталог cert_bundle (тот же состав, что внутри .tar.gz)."""
    d = ROOT / "artifacts" / "cert_bundle"
    assert d.is_dir(), "ожидается artifacts/cert_bundle после prepare_certification_bundle.sh"
    return d


def _expected_cost_from_cert_tree(cert_root: Path) -> tuple[float, float]:
    """(без тяжёлого множителя, итог с apply_heavy_dep_multiplier) — как в Регуляторе."""
    sbom_tcb = cert_root / "sbom" / "SBOM_TCB.cdx.json"
    sbom_other = cert_root / "sbom" / "SBOM_OTHER.cdx.json"
    abu_pkg = cert_root / "source" / "abu"
    req_path = cert_root / "source" / "requirements.txt"
    manifest_path = cert_root / "manifest.json"
    ipc_u = ipc_t = 0
    if manifest_path.is_file():
        mj = json.loads(manifest_path.read_text(encoding="utf-8"))
        ipc_u = max(0, int(mj.get("domain_ipc_untrusted_boundary_edges", 0)))
        ipc_t = max(0, int(mj.get("domain_ipc_trusted_boundary_edges", 0)))
    n_tcb, e_tcb = count_sbom_metrics(sbom_tcb)
    n_other, e_other = count_sbom_metrics(sbom_other)
    tcb_loc, tcb_cc = compute_tcb_source_metrics(abu_pkg)
    base = total_estimated_cost(
        n_tcb,
        e_tcb,
        n_other,
        e_other,
        tcb_loc=tcb_loc,
        tcb_cyclomatic_sum=tcb_cc,
        ipc_untrusted_boundary_edges=ipc_u,
        ipc_trusted_boundary_edges=ipc_t,
    )
    full = apply_heavy_dep_multiplier(base, sbom_tcb, req_path)
    return base, full


def test_starting_point_sbom_tcb_includes_numpy_heavy_multiplier_doubles_base(
    cert_bundle_dir: Path,
) -> None:
    """Без изоляции numpy в SBOM_TCB попадает в ДВБ; множитель удваивает базовую стоимость."""
    sbom_tcb = cert_bundle_dir / "sbom" / "SBOM_TCB.cdx.json"
    req = cert_bundle_dir / "source" / "requirements.txt"
    assert sbom_has_heavy_dep(sbom_tcb), "заготовка должна декларировать numpy в SBOM_TCB"
    base, full = _expected_cost_from_cert_tree(cert_bundle_dir)
    assert full == pytest.approx(base * HEAVY_DEP_COST_MULTIPLIER)
    # Только SBOM уже даёт множитель; дубль из requirements не меняет формулу
    assert apply_heavy_dep_multiplier(base, sbom_tcb, req) == full


def test_starting_point_certification_api_success_cost_matches_model_and_is_high(
    bundle_path: Path,
    cert_bundle_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST сертификации: успех, certificate_id = SHA-256, estimated_cost согласован с cost_model."""
    monkeypatch.setenv("REGULATOR_COV_FAIL_UNDER", "60")
    monkeypatch.setenv("REGULATOR_SECURITY_COV_FAIL_UNDER", "60")
    base, expected_full = _expected_cost_from_cert_tree(cert_bundle_dir)
    assert expected_full > STARTING_POINT_MIN_CERT_COST
    assert expected_full > base

    from regulator.main import app

    expected_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    client = TestClient(app)
    r = client.post(
        "/api/v1/certification/requests",
        json={
            "bundle_path": str(bundle_path.resolve()),
            "developer_company": "E2E starting_point",
            "firmware_label": "abu-sp-e2e",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert body.get("certificate_id") == expected_hash
    assert float(body.get("estimated_cost", 0)) == pytest.approx(expected_full, rel=1e-9, abs=0.01)
    assert float(body.get("estimated_cost", 0)) >= STARTING_POINT_MIN_CERT_COST
    assert body.get("developer_company") == "E2E starting_point"


def test_starting_point_dm_mission_reaches_abu(dm_client_e2e: TestClient) -> None:
    """ЦР → АБУ (заготовка через pythonpath): миссия доходит до abu.app и принимается."""
    r1 = dm_client_e2e.post(
        "/api/v1/rigs",
        json={
            "rig_id": "e2e-sp-rig",
            "abu_base_url": "http://127.0.0.1:8081",
            "certificate_id": None,
        },
    )
    assert r1.status_code == 200, r1.text

    r2 = dm_client_e2e.post(
        "/api/v1/missions",
        json={"rig_id": "e2e-sp-rig", "target_depth_m": 10.0, "max_rpm": 160.0},
    )
    assert r2.status_code == 200, r2.text
    abu_resp = (r2.json().get("abu_response") or {})
    assert abu_resp.get("accepted") is True
    assert abu_resp.get("mission_id")
