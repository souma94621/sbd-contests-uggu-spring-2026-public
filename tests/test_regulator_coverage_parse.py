"""Парсер покрытия abu/tcb vs abu/other в sandbox Регулятора."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_REG = str(ROOT / "external_systems" / "regulator")
if _REG not in sys.path:
    sys.path.insert(0, _REG)


def test_aggregate_splits_tcb_other() -> None:
    from regulator.sandbox import _aggregate_tcb_other_percent

    log = """
Name                           Stmts   Miss  Cover
--------------------------------------------------
abu/tcb/foo.py                    40     10    75%
abu/other/bar.py                   60     20    67%
--------------------------------------------------
TOTAL                            100     30    70%
"""

    tc, oc = _aggregate_tcb_other_percent(log, flat_legacy=False)
    assert tc == 75.0
    assert oc == pytest.approx(100.0 * 40.0 / 60.0, rel=0, abs=0.02)


def test_aggregate_flat_legacy_counts_as_tcb() -> None:
    from regulator.sandbox import _aggregate_tcb_other_percent

    log = """
Name                           Stmts   Miss  Cover
--------------------------------------------------
abu/app.py                        10      1    90%
--------------------------------------------------
TOTAL                             10      1    90%
"""

    tc, oc = _aggregate_tcb_other_percent(log, flat_legacy=True)
    assert tc == 90.0
    assert oc == 100.0
