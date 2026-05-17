"""Unit-тест формулы стоимости SBOM_TCB + SBOM_OTHER."""

from __future__ import annotations

from pathlib import Path

import pytest

from regulator.cost_model import (
    SBOM_OTHER_COST_DIVISOR,
    apply_heavy_dep_multiplier,
    estimate_other_sbom_cost,
    estimate_tcb_sbom_cost,
    total_estimated_cost,
)


def test_total_cost_tcb_plus_other_divisor() -> None:
    """Итог = cost_tcb (только рёбра TCB) + cost_other (только рёбра OTHER) / 100."""
    n_tcb, e_tcb = 2, 3
    n_other, e_other = 4, 5
    raw = total_estimated_cost(n_tcb, e_tcb, n_other, e_other)
    c_tcb = estimate_tcb_sbom_cost(e_tcb)
    c_other = estimate_other_sbom_cost(e_other)
    assert raw == pytest.approx(c_tcb + c_other / SBOM_OTHER_COST_DIVISOR)


def test_tcb_cost_independent_of_component_count() -> None:
    """При одинаковом E стоимость TCB не растёт с N (дробление доменов не штрафуется)."""
    e = 5
    a = total_estimated_cost(2, e, 0, 0)
    b = total_estimated_cost(200, e, 0, 0)
    assert a == pytest.approx(b)


def test_heavy_numpy_multiplier(tmp_path: Path) -> None:
    """При numpy в SBOM_TCB стоимость удваивается."""
    sbom = tmp_path / "tcb.cdx.json"
    sbom.write_text(
        '{"components": [{"name": "numpy"}], "dependencies": []}',
        encoding="utf-8",
    )
    base = 1000.0
    assert apply_heavy_dep_multiplier(base, sbom, None) == 2000.0
    assert apply_heavy_dep_multiplier(base, tmp_path / "missing.json", None) == 1000.0
