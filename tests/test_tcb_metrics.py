"""Тесты метрик исходников ДВБ (LOC, цикломатика) для Регулятора."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_REG = str(ROOT / "external_systems" / "regulator")
if _REG not in sys.path:
    sys.path.insert(0, _REG)


def test_count_loc_and_cyclomatic_trivial(tmp_path: Path) -> None:
    """Один файл, одна простая функция."""
    from regulator.tcb_metrics import compute_tcb_source_metrics

    pkg = tmp_path / "abu"
    pkg.mkdir()
    (pkg / "m.py").write_text(
        textwrap.dedent(
            '''
            def f():
                return 1
            '''
        ).strip(),
        encoding="utf-8",
    )
    loc, cc = compute_tcb_source_metrics(pkg)
    assert loc == 2  # две строки
    assert cc == 1  # одна функция, сложность 1


def test_cyclomatic_branches(tmp_path: Path) -> None:
    """If и BoolOp увеличивают суммарную сложность."""
    from regulator.tcb_metrics import compute_tcb_source_metrics

    pkg = tmp_path / "abu"
    pkg.mkdir()
    (pkg / "x.py").write_text(
        textwrap.dedent(
            '''
            def g(x):
                if x:
                    return 1 and 2
                return 0
            '''
        ).strip(),
        encoding="utf-8",
    )
    _loc, cc = compute_tcb_source_metrics(pkg)
    assert cc >= 3  # база + if + and



def test_split_abu_other_counts_only_tcb_for_metrics(tmp_path: Path) -> None:
    """При наличии abu/tcb и abu/other сумма строк и CC только под abu/tcb."""
    from regulator.tcb_metrics import compute_tcb_source_metrics

    root = tmp_path / "abu"
    tcb = root / "tcb"
    other = root / "other"
    tcb.mkdir(parents=True)
    other.mkdir(parents=True)
    (tcb / "trusted.py").write_text("print(1)\nprint(2)\n", encoding="utf-8")
    (other / "junk.py").write_text("print(3)\n" * 40, encoding="utf-8")

    loc, _cc = compute_tcb_source_metrics(root)
    assert loc == len((tcb / "trusted.py").read_text(encoding="utf-8").splitlines())


def test_flat_abu_when_no_other_dir_counts_all(tmp_path: Path) -> None:
    """Нет второго каталога — весь код abu считается ДВБ."""
    from regulator.tcb_metrics import compute_tcb_source_metrics

    root = tmp_path / "abu"
    tcb_only = root / "tcb"
    tcb_only.mkdir(parents=True)
    (tcb_only / "a.py").write_text("#x\n", encoding="utf-8")
    (root / "root.py").write_text("#z\n", encoding="utf-8")

    loc, _ = compute_tcb_source_metrics(root)
    assert loc >= 2


def test_tcb_source_cost_addon_matches_formula() -> None:
    """Аддитивная часть по LOC и K согласована с cost_model."""
    from regulator.cost_model import CC_COST_PER_POINT, LOC_COST_PER_LINE, tcb_source_cost_addon

    assert tcb_source_cost_addon(100, 50) == pytest.approx(
        100 * LOC_COST_PER_LINE + 50 * CC_COST_PER_POINT
    )

