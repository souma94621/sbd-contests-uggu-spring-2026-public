#!/usr/bin/env python3
"""
Сводная оценка: жюри кладёт копию ``src_solution`` каждого участника в
``evaluation/solution_<ID>``.

Сценарий поддерживает три режима:

* обычный пакетный прогон всех решений с генерацией сводки;
* распределённый прогон шарда с записью переносимых JSON-артефактов;
* сведение ранее собранных артефактов в Markdown/CSV/HTML.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from regulator_certification import summary_certification_cell

RAW_MAX_DEFAULT = 75.0
DEFAULT_RUN_ID = "latest"
JURY_COMMENT = "авто: C01-C19/C16 по логам; C20-C22 и текст - поручение жюри"
NUMBER_TYPES = (int, float)


def _main_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _evaluation_root(main: Path) -> Path:
    return main / "evaluation"


def _report_dir(main: Path) -> Path:
    return _evaluation_root(main) / "report"


def _default_artifacts_dir(main: Path, run_id: str) -> Path:
    return _report_dir(main) / "runs" / run_id


def _discover_solution_dirs(eval_root: Path) -> list[Path]:
    if not eval_root.is_dir():
        return []
    skip = {"report", ".git"}
    out: list[Path] = []
    for p in sorted(eval_root.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_dir():
            continue
        if p.name in skip or p.name.startswith("."):
            continue
        out.append(p)
    return out


def _solution_map(solutions: list[Path]) -> dict[str, Path]:
    return {p.name: p for p in solutions}


def _md_cell(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .strip()
    )


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    return safe.strip("._") or "solution"


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _cert_cell_from_json(data: dict[str, Any]) -> str:
    cer = data.get("certification")
    if cer is None:
        return "- (блок сертификации отключён)"
    if isinstance(cer, dict):
        pr_err = ""
        if not cer.get("prepare_ok"):
            pr_err = (cer.get("prepare_error") or "") or ""
        return summary_certification_cell(
            cer.get("regulator") or {},
            pr_err,
        )
    return "-"


def _criterion_scores(data: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in data.get("criteria") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        match = re.match(r"^(C\d\d)\s*:", name)
        if not match:
            continue
        try:
            out[match.group(1)] = float(item.get("score", 0))
        except (TypeError, ValueError):
            out[match.group(1)] = 0.0
    return out


def _runtime_env_for_solution(
    main_root: Path,
    solution_name: str,
    overlay: Path,
) -> dict[str, str]:
    """Санитарное окружение для прогона одного решения."""
    env = os.environ.copy()
    for key in (
        "CONTEST_REPO_ROOT",
        "PYTEST_ADDOPTS",
        "COVERAGE_FILE",
        "COVERAGE_PROCESS_START",
        "COVERAGE_RCFILE",
    ):
        env.pop(key, None)
    runtime = main_root / ".tmp_eval" / "runtime" / solution_name
    tmp_dir = runtime / "tmp"
    cache_dir = runtime / "cache"
    pycache_dir = runtime / "pycache"
    pipenv_cache_dir = cache_dir / "pipenv"
    for path in (tmp_dir, cache_dir, pycache_dir, pipenv_cache_dir):
        path.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(tmp_dir)
    env["TEMP"] = str(tmp_dir)
    env["TMP"] = str(tmp_dir)
    env["XDG_CACHE_HOME"] = str(cache_dir)
    env["PYTHONPYCACHEPREFIX"] = str(pycache_dir)
    env["PIPENV_CACHE_DIR"] = str(pipenv_cache_dir)
    env["CONTEST_MERGE_PARENT"] = str(
        main_root / ".tmp_eval" / "merge" / solution_name,
    )
    env["CONTEST_ORGANIZER_ROOT"] = str(main_root)
    env["CONTEST_PARTICIPANT_SRC_SOLUTION"] = str(overlay.resolve())
    return env


def _atomic_write(path: Path, content: str) -> None:
    """Атомарная запись файла, безопасная при конкурирующих прогонах."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _clear_run_artifacts(artifacts_dir: Path) -> None:
    for subdir, pattern in (("parts", "*.json"), ("details", "*.md")):
        target = artifacts_dir / subdir
        if not target.is_dir():
            continue
        for path in target.glob(pattern):
            if path.is_file():
                path.unlink()


def _shards_for_solutions(
    solutions: list[Path],
    shard_count: int,
) -> list[list[str]]:
    if shard_count < 1:
        raise ValueError("shard_count должен быть положительным")
    if solutions and shard_count > len(solutions):
        raise ValueError("число шардов не должно превышать число решений")
    shards: list[list[str]] = [[] for _ in range(shard_count)]
    for idx, solution in enumerate(solutions):
        shards[idx % shard_count].append(solution.name)
    return shards


def write_shard_plan(
    path: Path,
    main_root: Path,
    solutions: list[Path],
    shard_count: int,
    run_id: str,
) -> None:
    shards = _shards_for_solutions(solutions, shard_count)
    data = {
        "run_id": run_id,
        "shard_count": shard_count,
        "generated_at_utc": _utc_stamp(),
        "organizer_root": str(main_root.resolve()),
        "solutions_root": _relpath(_evaluation_root(main_root), main_root),
        "shards": [
            {
                "index": idx,
                "solutions": names,
            }
            for idx, names in enumerate(shards)
        ],
    }
    _atomic_write_json(path, data)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"не удалось разобрать JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: ожидается JSON-объект")
    return data


def load_shard_plan(
    path: Path,
    available: dict[str, Path],
) -> dict[int, list[Path]]:
    data = _load_json(path)
    try:
        shard_count = int(data["shard_count"])
    except (KeyError, TypeError, ValueError) as exc:
        msg = "в shard-plan отсутствует корректный shard_count"
        raise ValueError(msg) from exc
    if shard_count < 1:
        raise ValueError("shard_count должен быть положительным")

    shards_raw = data.get("shards")
    if not isinstance(shards_raw, list):
        raise ValueError("в shard-plan поле shards должно быть списком")

    seen_indexes: set[int] = set()
    seen_solutions: set[str] = set()
    shards: dict[int, list[Path]] = {}
    for item in shards_raw:
        if not isinstance(item, dict):
            raise ValueError("каждый элемент shards должен быть объектом")
        try:
            index = int(item["index"])
        except (KeyError, TypeError, ValueError) as exc:
            msg = "каждый шард должен иметь числовой index"
            raise ValueError(msg) from exc
        if index < 0 or index >= shard_count:
            raise ValueError(f"индекс шарда вне диапазона: {index}")
        if index in seen_indexes:
            raise ValueError(f"дублируется индекс шарда: {index}")
        seen_indexes.add(index)

        names = item.get("solutions")
        if not isinstance(names, list):
            raise ValueError(f"shards[{index}].solutions должен быть списком")
        if not names:
            raise ValueError(f"шард {index} пуст")
        selected: list[Path] = []
        for raw_name in names:
            name = str(raw_name)
            if name in seen_solutions:
                raise ValueError(
                    f"решение {name} указано более чем в одном шарде",
                )
            if name not in available:
                raise ValueError(f"каталог решения не найден: {name}")
            seen_solutions.add(name)
            selected.append(available[name])
        shards[index] = selected

    missing_indexes = set(range(shard_count)) - seen_indexes
    if missing_indexes:
        missing = ", ".join(str(x) for x in sorted(missing_indexes))
        raise ValueError(f"в shard-plan отсутствуют шарды: {missing}")
    return shards


def _select_solutions(
    all_solutions: list[Path],
    shard_index: int | None,
    shard_count: int | None,
    shard_plan: Path | None,
) -> list[Path]:
    if shard_plan is not None:
        if shard_index is None:
            raise ValueError("для --shard-plan нужно указать --shard-index")
        shards = load_shard_plan(shard_plan, _solution_map(all_solutions))
        if shard_index not in shards:
            raise ValueError(f"в shard-plan нет шарда {shard_index}")
        return shards[shard_index]

    if shard_index is None and shard_count is None:
        return all_solutions
    if shard_index is None or shard_count is None:
        msg = "--shard-index и --shard-count нужно указывать вместе"
        raise ValueError(msg)
    if shard_count < 1:
        raise ValueError("--shard-count должен быть положительным")
    if shard_index < 0 or shard_index >= shard_count:
        msg = "--shard-index должен быть в диапазоне [0, shard_count)"
        raise ValueError(msg)
    return [
        p
        for idx, p in enumerate(all_solutions)
        if idx % shard_count == shard_index
    ]


def _result_artifact_path(artifacts_dir: Path, solution_name: str) -> Path:
    return artifacts_dir / "parts" / f"{_safe_name(solution_name)}.json"


def _detail_artifact_path(artifacts_dir: Path, solution_name: str) -> Path:
    filename = f"detailed_result_{_safe_name(solution_name)}.md"
    return artifacts_dir / "details" / filename


def _base_result(
    *,
    main_root: Path,
    artifacts_dir: Path,
    solution: Path,
    shard_index: int | None,
    run_id: str,
) -> dict[str, Any]:
    detail_path = _detail_artifact_path(artifacts_dir, solution.name)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at_utc": _utc_stamp(),
        "shard_index": shard_index,
        "solution_name": solution.name,
        "solution_path": _relpath(solution, main_root),
        "detail_report": _relpath(detail_path, main_root),
        "status": "pending",
        "raw_sum": None,
        "raw_max": RAW_MAX_DEFAULT,
        "score_percent": None,
        "certification_cell": "-",
        "comment": JURY_COMMENT,
        "criteria_scores": {},
        "criteria": [],
    }


def run_solution(
    *,
    main_root: Path,
    scripts_dir: Path,
    artifacts_dir: Path,
    solution: Path,
    run_id: str,
    shard_index: int | None,
    no_pytest: bool,
    no_certification: bool,
) -> dict[str, Any]:
    detail_path = _detail_artifact_path(artifacts_dir, solution.name)
    detail_tmp = detail_path.parent / f".tmp_{detail_path.name}.{uuid4().hex}"
    argv = [
        sys.executable,
        str(scripts_dir / "evaluate_contest_score.py"),
        "--json",
        "--write-detailed",
        str(detail_tmp),
    ]
    if not no_certification:
        argv.append("--with-certification")
    if no_pytest:
        argv.append("--no-pytest")

    result = _base_result(
        main_root=main_root,
        artifacts_dir=artifacts_dir,
        solution=solution,
        shard_index=shard_index,
        run_id=run_id,
    )
    result["command"] = argv

    env = _runtime_env_for_solution(main_root, solution.name, solution)
    proc = subprocess.run(
        argv,
        cwd=str(main_root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    stderr_tail = (proc.stderr or "")[-1200:]
    result["returncode"] = proc.returncode
    result["stderr_tail"] = stderr_tail

    if proc.returncode != 0:
        if detail_tmp.exists():
            detail_tmp.unlink()
        result["status"] = "failed"
        result["comment"] = (
            f"Ошибка прогона: код {proc.returncode}; {stderr_tail}"
        ).strip()
        artifact_path = _result_artifact_path(artifacts_dir, solution.name)
        _atomic_write_json(artifact_path, result)
        return result

    if detail_tmp.exists():
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_tmp.replace(detail_path)

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        result["status"] = "invalid_json"
        result["comment"] = f"не удалось разобрать JSON: {exc}"
        artifact_path = _result_artifact_path(artifacts_dir, solution.name)
        _atomic_write_json(artifact_path, result)
        return result

    raw = float(data.get("raw_sum", 0))
    raw_max = float(data.get("raw_max", RAW_MAX_DEFAULT))
    percent = raw / raw_max * 100 if raw_max else 0.0
    result.update(
        {
            "status": "ok",
            "raw_sum": raw,
            "raw_max": raw_max,
            "score_percent": percent,
            "certification_cell": _cert_cell_from_json(data),
            "criteria_scores": _criterion_scores(data),
            "criteria": data.get("criteria") or [],
            "eval_root": data.get("eval_root"),
            "participant_overlay": data.get("participant_overlay"),
        },
    )
    artifact_path = _result_artifact_path(artifacts_dir, solution.name)
    _atomic_write_json(artifact_path, result)
    return result


def run_solutions(
    *,
    main_root: Path,
    scripts_dir: Path,
    artifacts_dir: Path,
    solutions: list[Path],
    run_id: str,
    shard_index: int | None,
    jobs: int,
    no_pytest: bool,
    no_certification: bool,
) -> list[dict[str, Any]]:
    if jobs < 1:
        raise ValueError("--jobs должен быть положительным")
    kwargs = {
        "main_root": main_root,
        "scripts_dir": scripts_dir,
        "artifacts_dir": artifacts_dir,
        "run_id": run_id,
        "shard_index": shard_index,
        "no_pytest": no_pytest,
        "no_certification": no_certification,
    }
    if jobs == 1:
        return [
            run_solution(solution=solution, **kwargs)
            for solution in solutions
        ]

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(
                run_solution,
                solution=solution,
                **kwargs,
            ): solution.name
            for solution in solutions
        }
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(
        results,
        key=lambda item: str(item.get("solution_name", "")).lower(),
    )


def load_artifact_results(artifacts_dir: Path) -> list[dict[str, Any]]:
    parts_dir = artifacts_dir / "parts"
    if not parts_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(parts_dir.glob("*.json"), key=lambda p: p.name.lower()):
        data = _load_json(path)
        data["_artifact_path"] = path.as_posix()
        results.append(data)
    return sorted(
        results,
        key=lambda item: str(item.get("solution_name", "")).lower(),
    )


def _score_text(result: dict[str, Any]) -> str:
    if result.get("status") != "ok":
        return "-"
    raw = float(result.get("raw_sum") or 0)
    raw_max = float(result.get("raw_max") or RAW_MAX_DEFAULT)
    return f"{raw:.1f} / {raw_max:.0f}"


def _result_comment(result: dict[str, Any]) -> str:
    comment = str(result.get("comment") or "")
    if result.get("status") == "ok":
        return comment or JURY_COMMENT
    return comment or f"прогон завершился со статусом {result.get('status')}"


def _result_columns(results: list[dict[str, Any]]) -> list[str]:
    criteria: set[str] = set()
    for result in results:
        scores = result.get("criteria_scores") or {}
        if isinstance(scores, dict):
            criteria.update(str(k) for k in scores)
    return sorted(criteria)


def _report_href(detail: str, main_root: Path, report_dir: Path) -> str:
    if not detail:
        return ""
    detail_path = Path(detail)
    if not detail_path.is_absolute():
        detail_path = main_root / detail_path
    return os.path.relpath(detail_path, report_dir)


def _write_summary_md(
    path: Path,
    *,
    main_root: Path,
    artifacts_dir: Path,
    results: list[dict[str, Any]],
    criteria_columns: list[str],
) -> None:
    table_header = [
        "решение №",
        "название каталога",
        "статус",
        "набрано баллов по результатам оценки",
        "процент",
        "стоимость сертификации",
        "подробный отчёт",
        "комментарии и оценки жюри",
        *criteria_columns,
    ]
    align = [
        ":---:",
        ":---",
        ":---",
        "---:",
        "---:",
        ":---",
        ":---",
        ":---",
        *("---:" for _ in criteria_columns),
    ]

    lines = [
        "# Сводный отчёт по оценке решений участников\n\n",
        f"Дата и время генерации (UTC): `{_utc_stamp()}`\n\n",
        "Каждый каталог `evaluation/solution_<ID>` задаёт содержимое "
        "**`src_solution`** участника поверх эталонного дерева этого "
        f"репозитория (`{main_root.name}`).\n"
        "Переносимые артефакты распределённой оценки лежат в `"
        f"{_relpath(artifacts_dir, main_root)}`.\n\n",
        "Сортируемая таблица: `summary.html`; табличный формат: "
        "`summary.csv`.\n\n",
        "| " + " | ".join(table_header) + " |\n",
        "| " + " | ".join(align) + " |\n",
    ]
    for idx, result in enumerate(results, start=1):
        scores = result.get("criteria_scores") or {}
        detail = str(result.get("detail_report") or "")
        detail_href = _report_href(detail, main_root, path.parent)
        detail_cell = f"[отчёт]({detail_href})" if detail_href else "-"
        percent = result.get("score_percent")
        row = [
            str(idx),
            str(result.get("solution_name") or ""),
            str(result.get("status") or ""),
            _score_text(result),
            f"{float(percent):.1f}%"
            if isinstance(percent, NUMBER_TYPES)
            else "-",
            str(result.get("certification_cell") or "-"),
            detail_cell,
            _result_comment(result),
            *(
                f"{float(scores[cid]):g}" if cid in scores else "-"
                for cid in criteria_columns
            ),
        ]
        lines.append(
            "| " + " | ".join(_md_cell(cell) for cell in row) + " |\n",
        )
    _atomic_write(path, "".join(lines))


def _write_summary_csv(
    path: Path,
    *,
    results: list[dict[str, Any]],
    criteria_columns: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "номер",
                "каталог",
                "статус",
                "баллы",
                "максимум",
                "процент",
                "сертификация",
                "подробный_отчет",
                "комментарий",
                *criteria_columns,
            ],
        )
        for idx, result in enumerate(results, start=1):
            scores = result.get("criteria_scores") or {}
            writer.writerow(
                [
                    idx,
                    result.get("solution_name") or "",
                    result.get("status") or "",
                    (
                        result.get("raw_sum")
                        if result.get("raw_sum") is not None
                        else ""
                    ),
                    (
                        result.get("raw_max")
                        if result.get("raw_max") is not None
                        else ""
                    ),
                    (
                        result.get("score_percent")
                        if result.get("score_percent") is not None
                        else ""
                    ),
                    result.get("certification_cell") or "",
                    result.get("detail_report") or "",
                    _result_comment(result),
                    *(scores.get(cid, "") for cid in criteria_columns),
                ],
            )
    tmp.replace(path)


def _html_sort_value(value: Any) -> str:
    if isinstance(value, NUMBER_TYPES):
        return str(value)
    if value is None:
        return ""
    return str(value)


def _write_summary_html(
    path: Path,
    *,
    main_root: Path,
    results: list[dict[str, Any]],
    criteria_columns: list[str],
) -> None:
    headers = [
        "№",
        "каталог",
        "статус",
        "баллы",
        "максимум",
        "процент",
        "сертификация",
        "подробный отчёт",
        "комментарий",
        *criteria_columns,
    ]
    rows: list[str] = []
    for idx, result in enumerate(results, start=1):
        scores = result.get("criteria_scores") or {}
        detail = str(result.get("detail_report") or "")
        detail_href = _report_href(detail, main_root, path.parent)
        link = (
            f'<a href="{html.escape(detail_href)}">отчёт</a>'
            if detail_href
            else ""
        )
        raw_sum = result.get("raw_sum")
        raw_max = result.get("raw_max")
        percent = result.get("score_percent")
        values: list[tuple[Any, str]] = [
            (idx, str(idx)),
            (
                result.get("solution_name") or "",
                str(result.get("solution_name") or ""),
            ),
            (
                result.get("status") or "",
                str(result.get("status") or ""),
            ),
            (
                raw_sum,
                "" if raw_sum is None else f"{float(raw_sum):.1f}",
            ),
            (
                raw_max,
                "" if raw_max is None else f"{float(raw_max):.0f}",
            ),
            (
                percent,
                "" if percent is None else f"{float(percent):.1f}%",
            ),
            (
                result.get("certification_cell") or "",
                str(result.get("certification_cell") or ""),
            ),
            (detail_href, link),
            (_result_comment(result), _result_comment(result)),
            *(
                (
                    scores.get(cid),
                    "" if cid not in scores else f"{float(scores[cid]):g}",
                )
                for cid in criteria_columns
            ),
        ]
        cells = []
        for sort_value, display in values:
            escaped = (
                display
                if display.startswith("<a ")
                else html.escape(display)
            )
            sort = html.escape(_html_sort_value(sort_value))
            cells.append(f'<td data-sort="{sort}">{escaped}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    header_html = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Сводная оценка решений</title>
<style>
body {{ font-family: sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{
  border: 1px solid #ccc;
  padding: 6px 8px;
  vertical-align: top;
}}
th {{ cursor: pointer; }}
td:nth-child(4),
td:nth-child(5),
td:nth-child(6) {{ text-align: right; }}
</style>
</head>
<body>
<h1>Сводная оценка решений участников</h1>
<p>Сгенерировано (UTC): <code>{html.escape(_utc_stamp())}</code></p>
<table id="summary">
<thead><tr>{header_html}</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<script>
const table = document.getElementById("summary");
for (const [index, th] of [...table.tHead.rows[0].cells].entries()) {{
  th.addEventListener("click", () => {{
    const rows = [...table.tBodies[0].rows];
    const direction = th.dataset.direction === "asc" ? -1 : 1;
    th.dataset.direction = direction === 1 ? "asc" : "desc";
    rows.sort((a, b) => {{
      const av = a.cells[index].dataset.sort || "";
      const bv = b.cells[index].dataset.sort || "";
      const an = Number(av);
      const bn = Number(bv);
      if (av !== "" && bv !== "" && !Number.isNaN(an) && !Number.isNaN(bn)) {{
        return (an - bn) * direction;
      }}
      return av.localeCompare(bv, "ru") * direction;
    }});
    table.tBodies[0].append(...rows);
  }});
}}
</script>
</body>
</html>
"""
    _atomic_write(path, body)


def write_empty_report(main_root: Path, report_dir: Path) -> None:
    eval_root = _evaluation_root(main_root)
    body = (
        "# Сводная оценка решений участников\n\n"
        f"Сгенерировано (UTC): `{_utc_stamp()}`\n\n"
        f"В `{eval_root.relative_to(main_root)!s}/` не найдено каталогов "
        "решений (ожидается `evaluation/solution_<ID>` с содержимым раздела "
        "**`src_solution`** "
        "участника).\n"
    )
    _atomic_write(report_dir / "summary.md", body)


def aggregate_results(
    *,
    main_root: Path,
    artifacts_dir: Path,
    report_dir: Path,
) -> list[dict[str, Any]]:
    results = load_artifact_results(artifacts_dir)
    criteria_columns = _result_columns(results)
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_summary_md(
        report_dir / "summary.md",
        main_root=main_root,
        artifacts_dir=artifacts_dir,
        results=results,
        criteria_columns=criteria_columns,
    )
    _write_summary_csv(
        report_dir / "summary.csv",
        results=results,
        criteria_columns=criteria_columns,
    )
    _write_summary_html(
        report_dir / "summary.html",
        main_root=main_root,
        results=results,
        criteria_columns=criteria_columns,
    )
    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Сводная таблица: evaluation/solution_* -> "
            "evaluation/report/summary.md, summary.csv и summary.html"
        ),
    )
    parser.add_argument(
        "--no-pytest",
        action="store_true",
        help="передать --no-pytest в evaluate_contest_score",
    )
    parser.add_argument(
        "--no-certification",
        action="store_true",
        help="не выполнять --with-certification (без пакета и API Регулятора)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="число параллельных прогонов",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        help="индекс текущего шарда, начиная с 0",
    )
    parser.add_argument("--shard-count", type=int, help="общее число шардов")
    parser.add_argument(
        "--shard-plan",
        type=Path,
        help="JSON-файл распределения решений",
    )
    parser.add_argument(
        "--write-shard-plan",
        type=Path,
        help="записать JSON-файл распределения и завершить работу",
    )
    parser.add_argument(
        "--run-id",
        default=DEFAULT_RUN_ID,
        help="идентификатор прогона",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="каталог переносимых артефактов",
    )
    parser.add_argument(
        "--aggregate",
        type=Path,
        help="свести результаты из указанного каталога",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    main_root = _main_repo_root()
    scripts_dir = main_root / "scripts"
    eval_root = _evaluation_root(main_root)
    report_dir = _report_dir(main_root)
    report_dir.mkdir(parents=True, exist_ok=True)

    artifacts_dir = (
        args.artifacts_dir
        if args.artifacts_dir is not None
        else _default_artifacts_dir(main_root, args.run_id)
    )

    try:
        if args.aggregate is not None:
            results = aggregate_results(
                main_root=main_root,
                artifacts_dir=args.aggregate,
                report_dir=report_dir,
            )
            print(
                f"{(report_dir / 'summary.md').resolve()} "
                f"({len(results)} решений)",
            )
            return 0

        solutions = _discover_solution_dirs(eval_root)
        if args.write_shard_plan is not None:
            write_shard_plan(
                args.write_shard_plan,
                main_root,
                solutions,
                int(args.shard_count or 1),
                args.run_id,
            )
            print(str(args.write_shard_plan.resolve()))
            return 0

        if not solutions:
            write_empty_report(main_root, report_dir)
            print((report_dir / "summary.md").as_posix(), file=sys.stderr)
            return 0

        selected = _select_solutions(
            solutions,
            args.shard_index,
            args.shard_count,
            args.shard_plan,
        )
        if args.shard_index is None and args.shard_plan is None:
            _clear_run_artifacts(artifacts_dir)
        run_solutions(
            main_root=main_root,
            scripts_dir=scripts_dir,
            artifacts_dir=artifacts_dir,
            solutions=selected,
            run_id=args.run_id,
            shard_index=args.shard_index,
            jobs=args.jobs,
            no_pytest=args.no_pytest,
            no_certification=args.no_certification,
        )

        # Обычный одиночный запуск сразу обновляет сводку. Шард на другой
        # машине только пишет артефакты; финальная машина запускает aggregate.
        if args.shard_index is None:
            results = aggregate_results(
                main_root=main_root,
                artifacts_dir=artifacts_dir,
                report_dir=report_dir,
            )
            print(
                f"{(report_dir / 'summary.md').resolve()} "
                f"({len(results)} решений)",
            )
        else:
            print(str(artifacts_dir.resolve()))
        return 0
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
