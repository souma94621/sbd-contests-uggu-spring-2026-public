"""Регулятор: разбиение ДВБ, политики IPC и выпуклый вклад по доменам."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
_REG = str(ROOT / "external_systems" / "regulator")
if _REG not in sys.path:
    sys.path.insert(0, _REG)


def test_total_cost_formula_decomposes_without_partition() -> None:
    """Без разбиения доменов total_estimated_cost совпадает с разложением на SBOM+лок+IPC."""
    from regulator.cost_model import (
        CC_COST_PER_POINT,
        LOC_COST_PER_LINE,
        SBOM_OTHER_COST_DIVISOR,
        estimate_domain_ipc_communication_cost,
        estimate_other_sbom_cost,
        estimate_tcb_sbom_cost,
        total_estimated_cost,
    )

    n_tcb, e_tcb, n_o, e_o = 2, 3, 4, 5
    ipc_u, ipc_t = 1, 2
    loc, cc = 100, 50
    expected = (
        estimate_tcb_sbom_cost(e_tcb)
        + LOC_COST_PER_LINE * loc
        + CC_COST_PER_POINT * cc
        + estimate_other_sbom_cost(e_o) / SBOM_OTHER_COST_DIVISOR
        + estimate_domain_ipc_communication_cost(ipc_u, ipc_t)
    )
    assert expected == pytest.approx(
        total_estimated_cost(
            n_tcb,
            e_tcb,
            n_o,
            e_o,
            tcb_loc=loc,
            tcb_cyclomatic_sum=cc,
            ipc_untrusted_boundary_edges=ipc_u,
            ipc_trusted_boundary_edges=ipc_t,
        ),
    )


def test_convex_partition_split_cheaper_than_one_bucket_same_total_loc_cc() -> None:
    """Две половины по LOC суммарно дешевле одной слитой конфигурации при той же сумме строк (выпуклость LOC² на домен)."""
    from regulator.cost_model import tcb_partition_verification_addon

    loc = 400
    cc_tot = 40
    one = tcb_partition_verification_addon([("m", loc, cc_tot)], {})[0]
    half_loc = loc // 2
    half_cc = cc_tot // 2
    two = tcb_partition_verification_addon(
        [("a", half_loc, half_cc), ("b", half_loc, half_cc)],
        {},
    )[0]
    assert two < one


def test_ipc_incoming_allowances_raise_domain_cost() -> None:
    """При прочих равных +R усиливает вклад домена через полином по R."""
    from regulator.cost_model import tcb_partition_verification_addon

    rows = [("svc", 200, 20)]
    c0 = tcb_partition_verification_addon(rows, {"svc": 0})[0]
    c3 = tcb_partition_verification_addon(rows, {"svc": 3})[0]
    c10 = tcb_partition_verification_addon(rows, {"svc": 10})[0]
    assert c3 > c0
    assert c10 > c3


def test_ipc_policy_counts_cross_only() -> None:
    """R_d считает только from≠to для целевого домена."""
    from regulator.ipc_policy_parse import count_incoming_cross_domain_ipc_allows

    pol = {"allows": [{"from": "a", "to": "b", "func": "f"}, {"from": "z", "to": "b", "func": "g"}]}
    c = count_incoming_cross_domain_ipc_allows(pol)
    assert c.get("b") == 2
    assert "a" not in c


def test_partition_residual(tmp_path: Path) -> None:
    """Неучтённые файлы идут в _residual."""
    from regulator.tcb_metrics import partition_tcb_into_domains

    mr = tmp_path / "tcb"
    mr.mkdir(parents=True)
    (mr / "core.py").write_text("pass\n", encoding="utf-8")
    (mr / "extra.py").write_text("pass\n", encoding="utf-8")

    spec = {"domains": [{"id": "core", "globs": ["core.py"]}]}
    rows, _w = partition_tcb_into_domains(mr, spec)
    ids = {r[0] for r in rows}
    assert "core" in ids and "_residual" in ids
