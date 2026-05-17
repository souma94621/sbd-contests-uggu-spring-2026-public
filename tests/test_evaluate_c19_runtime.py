"""Эвристика C19: разделение доменов по процессам."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_evaluate_module():
    p = ROOT / "scripts" / "evaluate_contest_score.py"
    spec = importlib.util.spec_from_file_location("evaluate_contest_score", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_c19_runtime_boundary_detects_multiprocessing() -> None:
    m = _load_evaluate_module()
    assert m._c19_runtime_process_boundary("from multiprocessing import Process\n") is True


def test_c19_runtime_boundary_detects_subprocess() -> None:
    m = _load_evaluate_module()
    assert m._c19_runtime_process_boundary("import subprocess\nsubprocess.run([])") is True


def test_c19_runtime_boundary_false_for_dirs_only() -> None:
    m = _load_evaluate_module()
    assert m._c19_runtime_process_boundary("abu/tcb/foo abu/other/bar domains monitor") is False
