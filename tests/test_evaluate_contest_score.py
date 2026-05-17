"""Калибровка скрипта оценки: корректная raw-сумма на базовой заготовке (без повторного pytest)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_evaluate_contest_score_calibration_no_pytest() -> None:
    """Быстрая проверка: сумма критериев для текущего дерева репозитория."""
    script = ROOT / "scripts" / "evaluate_contest_score.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--no-pytest", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    raw = float(data["raw_sum"])
    raw_max = float(data["raw_max"])
    assert 0.0 <= raw <= raw_max, f"raw вне диапазона [0, raw_max]: {raw} / {raw_max}"


def _run_eval_json(repo_root: Path) -> dict:
    script = ROOT / "scripts" / "evaluate_contest_score.py"
    env = os.environ.copy()
    # Тест не должен зависеть от merge-режима внешнего процесса оценки.
    env.pop("CONTEST_PARTICIPANT_SRC_SOLUTION", None)
    env.pop("CONTEST_ORGANIZER_ROOT", None)
    env["CONTEST_REPO_ROOT"] = str(repo_root)
    proc = subprocess.run(
        [sys.executable, str(script), "--no-pytest", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _score_for_criterion(data: dict, criterion_id: str) -> tuple[float, str]:
    for row in data["criteria"]:
        name = str(row["name"])
        if name.startswith(f"{criterion_id}:"):
            return float(row["score"]), str(row["note"])
    raise AssertionError(f"Критерий {criterion_id} не найден")


def test_c11_empty_main_requirements_with_other_gets_max_score(tmp_path: Path) -> None:
    src_solution = tmp_path / "src_solution"
    src_solution.mkdir(parents=True)
    (src_solution / "requirements.txt").write_text(
        "# ДВБ без внешних зависимостей\n",
        encoding="utf-8",
    )
    (src_solution / "requirements-other.txt").write_text(
        "fastapi==0.115.0\nnumpy==2.0.0\n",
        encoding="utf-8",
    )
    data = _run_eval_json(tmp_path)
    score, note = _score_for_criterion(data, "C11")
    assert score == 3.0
    assert "requirements-other.txt" in note


def test_c11_heavy_dependencies_in_main_requirements_get_zero(tmp_path: Path) -> None:
    src_solution = tmp_path / "src_solution"
    src_solution.mkdir(parents=True)
    (src_solution / "requirements.txt").write_text(
        "fastapi==0.115.0\nuvicorn==0.32.0\n",
        encoding="utf-8",
    )
    data = _run_eval_json(tmp_path)
    score, note = _score_for_criterion(data, "C11")
    assert score == 0.0
    assert "тяжёлые зависимости" in note
