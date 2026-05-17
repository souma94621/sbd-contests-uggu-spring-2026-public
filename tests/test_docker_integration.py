"""Интеграционные тесты против Регулятора в Docker (HTTP).

Требуются запущенные контейнеры: ./scripts/docker_up.sh
Переменная REGULATOR_URL (по умолчанию http://127.0.0.1:8082).
Пропуск: SKIP_DOCKER_TESTS=1 или недоступен health.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _skip_if_disabled() -> None:
    if os.environ.get("SKIP_DOCKER_TESTS", "").lower() in ("1", "true", "yes"):
        pytest.skip("SKIP_DOCKER_TESTS")


def _regulator_url() -> str:
    return os.environ.get("REGULATOR_URL", "http://127.0.0.1:8082").rstrip("/")


@pytest.fixture(scope="module")
def regulator_http() -> str:
    """Базовый URL Регулятора; пропуск, если сервис не отвечает."""
    _skip_if_disabled()
    url = _regulator_url()
    try:
        r = httpx.get(f"{url}/api/v1/health", timeout=5.0)
    except httpx.RequestError as exc:
        pytest.skip(f"Регулятор недоступен по {url}: {exc}")
    if r.status_code != 200:
        pytest.skip(f"Регулятор health: HTTP {r.status_code}")
    return url


@pytest.fixture(scope="module")
def bundle_path() -> Path:
    """Собирает пакет так же, как make prepare-cert-bundle."""
    subprocess.run(
        ["bash", str(ROOT / "scripts" / "prepare_certification_bundle.sh")],
        cwd=ROOT,
        check=True,
    )
    p = ROOT / "artifacts" / "abu_certification_bundle.tar.gz"
    assert p.is_file()
    return p


@pytest.mark.docker
def test_http_upload_certification_and_summary(
    regulator_http: str,
    bundle_path: Path,
) -> None:
    """POST /certification/upload и GET /certification/summary по HTTP."""
    with open(bundle_path, "rb") as f:
        files = {"bundle": ("abu_certification_bundle.tar.gz", f, "application/gzip")}
        data = {
            "developer_company": "Интеграционные тесты Docker",
            "firmware_label": "abu-test-fw",
        }
        r = httpx.post(
            f"{regulator_http}/api/v1/certification/upload",
            files=files,
            data=data,
            timeout=300.0,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True
    assert body.get("developer_company") == "Интеграционные тесты Docker"
    assert body.get("firmware_label") == "abu-test-fw"
    cid = body.get("certificate_id")
    assert cid and len(cid) == 64

    s = httpx.get(f"{regulator_http}/api/v1/certification/summary", timeout=10.0)
    assert s.status_code == 200
    rows = s.json()
    assert isinstance(rows, list)
    match = [x for x in rows if x.get("certificate_id") == cid]
    assert len(match) == 1
    assert match[0].get("developer_company") == "Интеграционные тесты Docker"
    assert float(match[0].get("estimated_cost", 0)) > 0


@pytest.mark.docker
def test_digital_mine_health_optional() -> None:
    """ЦР в compose (если поднят)."""
    _skip_if_disabled()
    url = os.environ.get("DIGITAL_MINE_URL", "http://127.0.0.1:8080").rstrip("/")
    try:
        r = httpx.get(f"{url}/api/v1/health", timeout=3.0)
    except httpx.RequestError:
        pytest.skip("ЦР не запущен (docker compose up digital_mine)")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
