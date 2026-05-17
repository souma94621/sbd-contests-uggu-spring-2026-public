from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_all_participant_repos.py"


def _load_module():
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "evaluate_all_participant_repos",
        SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


eval_all = _load_module()


def _make_solution(root: Path, name: str) -> Path:
    path = root / "evaluation" / name
    path.mkdir(parents=True)
    return path


def test_write_and_read_shard_plan_can_be_edited(tmp_path: Path) -> None:
    solutions = [
        _make_solution(tmp_path, "solution_01"),
        _make_solution(tmp_path, "solution_02"),
        _make_solution(tmp_path, "solution_03"),
        _make_solution(tmp_path, "solution_04"),
    ]
    plan_path = (
        tmp_path
        / "evaluation"
        / "report"
        / "runs"
        / "final"
        / "shard_plan.json"
    )

    eval_all.write_shard_plan(plan_path, tmp_path, solutions, 2, "final")
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    data["shards"][0]["solutions"] = ["solution_02"]
    data["shards"][1]["solutions"] = [
        "solution_01",
        "solution_03",
        "solution_04",
    ]
    plan_path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )

    shards = eval_all.load_shard_plan(
        plan_path,
        eval_all._solution_map(solutions),
    )

    assert [p.name for p in shards[0]] == ["solution_02"]
    assert [p.name for p in shards[1]] == [
        "solution_01",
        "solution_03",
        "solution_04",
    ]


def test_shard_plan_validation_rejects_duplicates(tmp_path: Path) -> None:
    solutions = [
        _make_solution(tmp_path, "solution_01"),
        _make_solution(tmp_path, "solution_02"),
    ]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "run_id": "final",
                "shard_count": 2,
                "shards": [
                    {"index": 0, "solutions": ["solution_01"]},
                    {"index": 1, "solutions": ["solution_01", "solution_02"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="более чем в одном шарде"):
        eval_all.load_shard_plan(plan_path, eval_all._solution_map(solutions))


def test_index_based_sharding_is_deterministic(tmp_path: Path) -> None:
    solutions = [
        _make_solution(tmp_path, "solution_01"),
        _make_solution(tmp_path, "solution_02"),
        _make_solution(tmp_path, "solution_03"),
        _make_solution(tmp_path, "solution_04"),
        _make_solution(tmp_path, "solution_05"),
    ]

    selected = eval_all._select_solutions(
        solutions,
        shard_index=1,
        shard_count=2,
        shard_plan=None,
    )

    assert [p.name for p in selected] == ["solution_02", "solution_04"]


def test_aggregate_results_writes_tables(tmp_path: Path) -> None:
    artifacts = tmp_path / "evaluation" / "report" / "runs" / "final"
    parts = artifacts / "parts"
    parts.mkdir(parents=True)
    (parts / "solution_01.json").write_text(
        json.dumps(
            {
                "solution_name": "solution_01",
                "status": "ok",
                "raw_sum": 61.5,
                "raw_max": 75.0,
                "score_percent": 82.0,
                "certification_cell": "1000 руб.",
                "detail_report": (
                    "evaluation/report/runs/final/details/"
                    "detailed_result_solution_01.md"
                ),
                "comment": "авто",
                "criteria_scores": {"C01": 3.0, "C02": 2.5},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (parts / "solution_02.json").write_text(
        json.dumps(
            {
                "solution_name": "solution_02",
                "status": "failed",
                "raw_sum": None,
                "raw_max": 75.0,
                "score_percent": None,
                "certification_cell": "",
                "detail_report": "",
                "comment": "Ошибка прогона",
                "criteria_scores": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_dir = tmp_path / "evaluation" / "report"

    results = eval_all.aggregate_results(
        main_root=tmp_path,
        artifacts_dir=artifacts,
        report_dir=report_dir,
    )

    assert [r["solution_name"] for r in results] == [
        "solution_01",
        "solution_02",
    ]
    assert "solution_01" in (report_dir / "summary.md").read_text(
        encoding="utf-8",
    )
    assert "C01" in (report_dir / "summary.csv").read_text(encoding="utf-8")
    html = (report_dir / "summary.html").read_text(encoding="utf-8")
    assert "data-sort" in html
    assert "addEventListener" in html


def test_makefile_has_distributed_evaluation_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "evaluate-shard-plan:",
        "evaluate-shard:",
        "evaluate-distributed-aggregate:",
        "evaluate-distributed-local:",
    ):
        assert target in makefile

    proc = subprocess.run(
        [
            "make",
            "-n",
            "evaluate-shard",
            "RUN_ID=final",
            "SHARD_INDEX=1",
            "SHARDS=3",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--shard-plan" in proc.stdout
    assert "--shard-index 1" in proc.stdout
