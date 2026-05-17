"""Тесты генерации SBOM из манифеста и согласованности с парсером Регулятора."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_generate_sbom_cyclonedx_structure_and_metrics(tmp_path: Path) -> None:
    """Сгенерированные файлы — CycloneDX; метрики совпадают с ожиданиями манифеста."""
    manifest = ROOT / "src_starting_point" / "sbom" / "sbom_manifest.json"
    out_tcb = tmp_path / "SBOM_TCB.cdx.json"
    out_other = tmp_path / "SBOM_OTHER.cdx.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_sbom_cdx.py"),
            "--manifest",
            str(manifest),
            "--out-tcb",
            str(out_tcb),
            "--out-other",
            str(out_other),
        ],
        cwd=str(ROOT),
        check=True,
    )
    for p in (out_tcb, out_other):
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data.get("bomFormat") == "CycloneDX"
        assert data.get("specVersion") == "1.5"
        assert "metadata" in data and "component" in data["metadata"]
        assert isinstance(data.get("components"), list)
        assert isinstance(data.get("dependencies"), list)

    sys.path.insert(0, str(ROOT / "external_systems" / "regulator"))
    from regulator.sbom_parse import count_sbom_metrics

    assert count_sbom_metrics(out_tcb) == (2, 1)
    assert count_sbom_metrics(out_other) == (4, 0)


def test_generate_sbom_cost_formula_matches_split(tmp_path: Path) -> None:
    """Итоговая стоимость по числам N/E из сгенерированного TCB/OTHER согласована с cost_model."""
    sys.path.insert(0, str(ROOT / "external_systems" / "regulator"))
    from regulator.cost_model import estimate_other_sbom_cost, estimate_tcb_sbom_cost, total_estimated_cost
    from regulator.sbom_parse import count_sbom_metrics

    manifest = ROOT / "src_starting_point" / "sbom" / "sbom_manifest.json"
    out_tcb = tmp_path / "tcb.cdx.json"
    out_other = tmp_path / "oth.cdx.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_sbom_cdx.py"),
            "--manifest",
            str(manifest),
            "--out-tcb",
            str(out_tcb),
            "--out-other",
            str(out_other),
        ],
        cwd=str(ROOT),
        check=True,
    )
    n_tcb, e_tcb = count_sbom_metrics(out_tcb)
    n_o, e_o = count_sbom_metrics(out_other)
    raw = total_estimated_cost(n_tcb, e_tcb, n_o, e_o)
    assert raw == pytest.approx(
        estimate_tcb_sbom_cost(e_tcb) + estimate_other_sbom_cost(e_o) / 100.0
    )
