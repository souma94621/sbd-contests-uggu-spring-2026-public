"""Gate REGULATOR_TCB_COV_REQUIRED в process_certification."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
_REG = str(ROOT / "external_systems" / "regulator")
if _REG not in sys.path:
    sys.path.insert(0, _REG)


@pytest.fixture(scope="module")
def bundle_path() -> Path:
    import subprocess

    subprocess.run(
        ["bash", str(ROOT / "scripts" / "prepare_certification_bundle.sh")],
        cwd=ROOT,
        check=True,
    )
    p = ROOT / "artifacts" / "abu_certification_bundle.tar.gz"
    assert p.is_file()
    return p


@patch("regulator.main.run_pytest_with_coverage")
def test_tcb_below_threshold_rejects_without_certificate(
    mock_pytest: object,
    bundle_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from regulator.sandbox import PytestCovResult

    monkeypatch.setenv("REGULATOR_TCB_COV_REQUIRED", "40")
    mock_pytest.return_value = PytestCovResult(
        ok=True,
        coverage_total=90.0,
        coverage_tcb=35.0,
        coverage_other=88.0,
        log="mock",
    )
    from regulator.main import process_certification

    out = process_certification(bundle_path)
    assert out.success is False
    assert out.certificate_id is None
    assert out.coverage_tcb_percent == 35.0
    assert "ниже требуемого" in (out.message or "")
    mock_pytest.assert_called_once()
