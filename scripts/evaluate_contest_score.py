#!/usr/bin/env python3
"""
Оценка по 25 критериям (макс. 3 балла каждый; номинальная сумма RAW_MAX).
Оцениваются в первую очередь изменения конкурсанта (src_solution/, тесты, отчётные артефакты).

Итог для отчёта: только сумма по критериям (raw) до RAW_MAX.

Запуск: из корня репозитория, после `make install`.
  pipenv run python scripts/evaluate_contest_score.py

Опции:
  --no-pytest      не запускать pytest (использовать только проверки артефактов)
  --json           вывести JSON со списком критериев (+ eval_root, participant_overlay)
  --write-detailed PATH   записать подробный Markdown по критериям (таблица и итог)
  --with-certification    собрать пакет решения и запросить локальный API Регулятора

Переопределение корня проверяемого репозитория:
  CONTEST_REPO_ROOT=/abs/path/to/checkout pipenv run python scripts/evaluate_contest_score.py

Режим «эталон + только src_solution участника» (как у жюри для evaluation/solution_<ID>):
  env -u CONTEST_REPO_ROOT CONTEST_ORGANIZER_ROOT=/abs/organizer \
    CONTEST_PARTICIPANT_SRC_SOLUTION=/abs/to/src_solution_tree pipenv run python ...

C09: flake8 по src_solution/ (при наличии .py).
C06: SBOM_TCB / SBOM_OTHER в заготовке (`src_starting_point/sbom`).
C14: numpy в SBOM решения (SBOM_TCB vs SBOM_OTHER), макс. 3.
C16: покрытие ДВБ решения из pytest с --cov=src_solution.abu.tcb (включая подпакет tcb.sys).
C17: эвристика полноты **src_solution/docs/solution.md** (fallback: шаблон в `src_starting_point/docs/`, указатель в `docs/`; без канона — ограничение баллов).

C18–C19: эвристики по доменам; C19 ставит упор на **процессы** (`multiprocessing`/`subprocess`), каталоги `tcb/other` только в пояснениях.

C20–C22: экспертные; в скрипте 0, жюри.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Все 25 критериев с максимумом 3
RAW_MAX = 75.0


def _repo_root() -> Path:
    """Каталог решения участника или эталона (env CONTEST_REPO_ROOT)."""
    override = os.environ.get("CONTEST_REPO_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[1]


ROOT = _repo_root()

E2E_TEST_PATH = ROOT / "tests" / "test_e2e_abu_dm_scenario.py"


def _sync_eval_root_globals(new_root: Path) -> None:
    """Обновить ROOT и производные пути (после merge или смены env)."""
    global ROOT, E2E_TEST_PATH
    ROOT = new_root.resolve()
    E2E_TEST_PATH = ROOT / "tests" / "test_e2e_abu_dm_scenario.py"


def _src_solution_snapshot() -> tuple[list[Path], str]:
    """Возвращает список .py под src_solution/ и объединённый текст (для эвристик)."""
    sol = ROOT / "src_solution"
    if not sol.is_dir():
        return [], ""
    try:
        py_files = [p for p in sol.rglob("*.py") if p.is_file()]
    except OSError:
        return [], ""
    if not py_files:
        return [], ""
    chunks: list[str] = []
    for p in py_files:
        try:
            chunks.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return py_files, "\n".join(chunks)


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file() or (ROOT / rel).is_dir()


def _solution_test_files_in_src_solution_tests() -> list[Path]:
    """Тесты решения, размещённые в каноническом каталоге src_solution/tests."""
    base = ROOT / "src_solution" / "tests"
    if not base.is_dir():
        return []
    return [p for p in base.rglob("test_*.py") if p.is_file()]


def _misplaced_solution_test_files() -> list[Path]:
    """Тесты под src_solution, расположенные вне src_solution/tests."""
    base = ROOT / "src_solution"
    tests_root = ROOT / "src_solution" / "tests"
    if not base.is_dir():
        return []
    misplaced: list[Path] = []
    for p in base.rglob("test_*.py"):
        if not p.is_file():
            continue
        if tests_root in p.parents:
            continue
        misplaced.append(p)
    return misplaced


def _parse_python_file(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return None


def _imports_src_solution(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src_solution"):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("src_solution"):
                return True
    return False


def _repo_test_roots() -> list[Path]:
    roots: list[Path] = []
    for rel in ("tests", "src_solution/tests"):
        p = ROOT / rel
        if p.is_dir():
            roots.append(p)
    return roots


def _test_files_importing_src_solution() -> list[Path]:
    found: list[Path] = []
    for tests_root in _repo_test_roots():
        for tp in tests_root.rglob("*.py"):
            if not tp.is_file():
                continue
            tree = _parse_python_file(tp)
            if tree and _imports_src_solution(tree):
                found.append(tp)
    return found


def _test_files_importing_event_log_and_src_solution() -> list[Path]:
    found: list[Path] = []
    for tests_root in _repo_test_roots():
        for tp in tests_root.rglob("*.py"):
            if not tp.is_file():
                continue
            tree = _parse_python_file(tp)
            if not tree:
                continue
            has_sol = _imports_src_solution(tree)
            has_el = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if "event_log" in a.name:
                            has_el = True
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if "event_log" in mod:
                        has_el = True
                    for a in node.names:
                        if "event_log" in (a.name or ""):
                            has_el = True
            if has_sol and has_el:
                found.append(tp)
    return found


def _count_test_functions(path: Path) -> int:
    tree = _parse_python_file(path)
    if not tree:
        return 0
    n = 0
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            n += 1
    return n


def _count_event_log_related_tests() -> int:
    """Число тестовых функций, проверяющих event_log/audit_log в src_solution/tests."""
    total = 0
    src_tests = ROOT / "src_solution" / "tests"
    if src_tests.is_dir():
        for tp in src_tests.rglob("test_*.py"):
            if not tp.is_file():
                continue
            try:
                body = tp.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
            if "event_log" in body or "audit_log" in body:
                total += _count_test_functions(tp)
    if total > 0:
        return total

    # fallback на пример в src_starting_point (только как ориентир)
    example_test = ROOT / "src_starting_point" / "tests" / "test_event_log.py"
    if example_test.is_file():
        return _count_test_functions(example_test)
    return 0


def _pytest_ini_has_security_marker() -> bool:
    p = ROOT / "pytest.ini"
    if not p.is_file():
        return False
    txt = p.read_text(encoding="utf-8", errors="replace")
    return "security" in txt.lower()


def _e2e_matches_operational_scenario() -> tuple[bool, str]:
    """Проверка, что e2e-тест отражает базовые шаги operational_scenario_v1."""
    if not E2E_TEST_PATH.is_file():
        return False, "нет tests/test_e2e_abu_dm_scenario.py"
    try:
        text = E2E_TEST_PATH.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False, "ошибка чтения e2e-теста"
    required_markers = (
        "/api/v1/rigs",
        "/api/v1/missions",
        "certificate_id",
        "mission_id",
    )
    missing = [m for m in required_markers if m not in text]
    if missing:
        return False, f"не хватает шагов сценария: {', '.join(missing)}"
    return True, "e2e покрывает регистрацию, допуск и выдачу миссии"


def _security_marker_used_in_tests() -> int:
    """Число тестовых файлов с @pytest.mark.security."""
    n = 0
    for base in (
        ROOT / "tests",
        ROOT / "src_starting_point" / "tests",
        ROOT / "src_solution" / "tests",
    ):
        if not base.is_dir():
            continue
        for tp in base.rglob("*.py"):
            if not tp.is_file():
                continue
            try:
                t = tp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "pytest.mark.security" in t or "@pytest.mark.security" in t:
                n += 1
    return n


def _c19_runtime_process_boundary(lower: str) -> bool:
    """
    Эвристика разделения доменов по **процессам** (выполнение), а не по каталогам.
    Каталоги `abu/tcb` и `abu/other` не учитываются здесь — см. логику выше в rubric.
    """
    if "multiprocessing" in lower:
        return True
    if re.search(r"\bsubprocess\b", lower):
        return True
    if "domain_process" in lower:
        return True
    return False


def score_c18_c19_solution(py_files: list[Path], blob: str) -> tuple[float, float, str, str]:
    """C18/C19: целые уровни 0–3 по признакам в коде и тестах (AST для тестов с src_solution)."""
    if not py_files and not blob.strip():
        return 0.0, 0.0, "src_solution отсутствует или пуст", "src_solution отсутствует или пуст"

    lower = blob.lower()
    path_blob = " ".join(str(p.relative_to(ROOT)).lower() for p in py_files)

    has_monitor_name = "security_monitor" in path_blob or "security_monitor" in lower
    has_policies_path = "policies" in path_blob or any(part == "policies" for p in py_files for part in p.parts)
    has_policies_code = "policies" in lower or "policy" in lower

    test_ast_hits = 0
    for tp in _test_files_importing_src_solution():
        tree = _parse_python_file(tp)
        if not tree:
            continue
        t = tp.read_text(encoding="utf-8", errors="replace").lower()
        if "security_monitor" in t or "policies" in t:
            test_ast_hits += 1

    c18_note_parts: list[str] = []
    if has_monitor_name:
        c18_note_parts.append("monitor")
    if has_policies_path or has_policies_code:
        c18_note_parts.append("policies")
    if test_ast_hits:
        c18_note_parts.append(f"тесты≈{test_ast_hits}")

    if has_monitor_name and (has_policies_path or has_policies_code) and test_ast_hits >= 2:
        c18 = 3.0
    elif has_monitor_name and (has_policies_path or has_policies_code) and test_ast_hits >= 1:
        c18 = 2.0
    elif has_monitor_name and (has_policies_path or has_policies_code):
        c18 = 1.0
    elif has_monitor_name or has_policies_path or has_policies_code:
        c18 = 1.0
    else:
        c18 = 0.0
    c18_note = ", ".join(c18_note_parts) if c18_note_parts else "нет признаков"

    has_domain = "domain" in path_blob or "domains" in path_blob or "domain" in lower
    has_monitor_word = "monitor" in lower or "mediator" in lower
    has_req_resp = "request" in lower and "response" in lower

    kw_sigs = int(has_domain) + int(has_monitor_word) + int(has_req_resp)

    runtime = _c19_runtime_process_boundary(lower)
    sol_abu = ROOT / "src_solution" / "abu"
    split_dirs = (
        sol_abu.is_dir()
        and (sol_abu / "tcb").is_dir()
        and (sol_abu / "other").is_dir()
    )

    c19_note_parts: list[str] = []
    if not split_dirs:
        c19_note_parts.append(
            "без пары каталогов `abu/tcb` и `abu/other` Регулятор относит строки/покрытие всего `abu` к ДВБ"
        )

    if runtime:
        c19_note_parts.append("процессы(multiprocessing/subprocess/DomainProcess)")
        if kw_sigs >= 3:
            c19 = 3.0
        elif kw_sigs == 2:
            c19 = 2.0
        elif kw_sigs == 1:
            c19 = 2.0
        else:
            c19 = 1.0
    else:
        c19_note_parts.append(
            "нет признаков разнесения доменов по отдельным процессам — кодовую базу следует оценивать "
            "как единую границу доверия (повышенные требования к покрытию и SBOM)"
        )
        if split_dirs:
            c19_note_parts.append(
                "каталоги `abu/tcb` и `abu/other` облегчают измерение покрытия, но не заменяют изоляцию по Process"
            )
        if kw_sigs >= 3:
            c19 = 2.0
        elif kw_sigs == 2:
            c19 = 1.0
        elif kw_sigs == 1:
            c19 = 1.0
        else:
            c19 = 0.0

    if has_domain:
        c19_note_parts.append("domains")
    if has_monitor_word:
        c19_note_parts.append("monitor")
    if has_req_resp:
        c19_note_parts.append("request/response")

    c19_note = ", ".join(c19_note_parts) if c19_note_parts else "нет признаков"

    return c18, c19, c18_note, c19_note


def _parse_total_coverage_percent(log: str) -> float | None:
    """Извлекает TOTAL %% из вывода pytest-cov."""
    for line in log.splitlines():
        if line.strip().startswith("TOTAL"):
            parts = line.split()
            for p in parts:
                if p.endswith("%"):
                    try:
                        return float(p.rstrip("%"))
                    except ValueError:
                        continue
    return None


def _parse_file_coverage_percent(log: str, file_name: str) -> float | None:
    """Извлекает процент покрытия для конкретного файла из вывода pytest-cov."""
    for line in log.splitlines():
        if file_name not in line:
            continue
        parts = line.split()
        for p in reversed(parts):
            if p.endswith("%"):
                try:
                    return float(p.rstrip("%"))
                except ValueError:
                    continue
    return None


def _eval_runtime_dir() -> Path:
    """Изолированный runtime-каталог оценщика под текущим ROOT."""
    runtime = ROOT / ".eval_runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def _base_subprocess_env() -> dict[str, str]:
    """Санитарное окружение для подпроцессов оценщика."""
    env = os.environ.copy()
    for key in (
        "PYTEST_ADDOPTS",
        "COVERAGE_FILE",
        "COVERAGE_PROCESS_START",
        "COVERAGE_RCFILE",
    ):
        env.pop(key, None)
    runtime = _eval_runtime_dir()
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
    env["CONTEST_REPO_ROOT"] = str(ROOT)
    env["CONTEST_PYTHON"] = sys.executable
    return env


def _run_pytest_suite(
    targets: list[str],
    with_cov: bool,
    cov_file: Path | None,
    base_env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Запускает pytest для одного набора тестов."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--import-mode=importlib",
        *targets,
    ]
    if with_cov:
        cmd.extend(
            [
                "--cov=src_solution.abu.tcb",
                "--cov=src_solution.abu.tcb.sys.security_monitor",
                "--cov-report=term-missing",
            ],
        )
    env = base_env.copy()
    if cov_file is not None:
        env["COVERAGE_FILE"] = str(cov_file)
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _coverage_report_from_parts(cov_parts: list[Path], base_env: dict[str, str]) -> str:
    """Комбинирует coverage-файлы и возвращает текст отчёта."""
    existing = [p for p in cov_parts if p.is_file()]
    if not existing:
        return ""
    env = base_env.copy()
    combined = _eval_runtime_dir() / ".coverage.combined"
    env["COVERAGE_FILE"] = str(combined)
    combine_cmd = [sys.executable, "-m", "coverage", "combine", *[str(p) for p in existing]]
    combine = subprocess.run(
        combine_cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if combine.returncode != 0:
        return (combine.stdout or "") + (combine.stderr or "")
    report = subprocess.run(
        [sys.executable, "-m", "coverage", "report", "-m", "-i"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return (report.stdout or "") + (report.stderr or "")


def run_pytest_with_tcb_coverage() -> tuple[int, float | None, float | None]:
    """Прогон pytest по независимым наборам с изолированным окружением."""
    base_env = _base_subprocess_env()
    suites = [
        ("sp", ["src_starting_point/tests"]),
        ("root", ["tests"]),
        ("sol", ["src_solution/tests"]),
    ]
    runtime = _eval_runtime_dir()
    cov_parts = [runtime / ".coverage.sp", runtime / ".coverage.root", runtime / ".coverage.sol"]

    cov_runs: list[subprocess.CompletedProcess[str]] = []
    unrecognized_cov = False
    first_nonzero = 0
    for (label, targets), cov_file in zip(suites, cov_parts, strict=True):
        proc = _run_pytest_suite(targets, with_cov=True, cov_file=cov_file, base_env=base_env)
        cov_runs.append(proc)
        run_log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 and first_nonzero == 0:
            first_nonzero = proc.returncode
        if proc.returncode == 4 and "unrecognized arguments: --cov" in run_log:
            unrecognized_cov = True

    if unrecognized_cov:
        first_nonzero = 0
        for _label, targets in suites:
            proc = _run_pytest_suite(targets, with_cov=False, cov_file=None, base_env=base_env)
            if proc.returncode != 0 and first_nonzero == 0:
                first_nonzero = proc.returncode
        return first_nonzero, None, None

    coverage_log = _coverage_report_from_parts(cov_parts, base_env)
    pct = _parse_total_coverage_percent(coverage_log)
    monitor_pct = _parse_file_coverage_percent(coverage_log, "security_monitor.py")
    return first_nonzero, pct, monitor_pct


def score_c16_tcb_coverage(pct: float | None, pytest_skipped: bool) -> tuple[float, str]:
    """Покрытие подкаталога src_solution/abu/tcb (ДВБ решения) тестами: пороги по TOTAL."""
    if pytest_skipped:
        return 0.0, "пропуск pytest"
    if pct is None:
        return 0.0, "нет данных coverage"
    if pct >= 80.0:
        return 3.0, f"{pct:.1f}% (≥80%)"
    if pct >= 60.0:
        return 2.0, f"{pct:.1f}% (60–79%)"
    if pct >= 40.0:
        return 1.0, f"{pct:.1f}% (40–59%)"
    return 0.0, f"{pct:.1f}% (<40%)"


def run_flake8_src_solution() -> tuple[int | None, str]:
    """flake8 по src_solution. Возвращает (число строк с замечаниями, None) или (None, причина)."""
    sol = ROOT / "src_solution"
    if not sol.is_dir():
        return None, "нет каталога"
    py_files = [p for p in sol.rglob("*.py") if p.is_file()]
    if not py_files:
        return None, "нет .py"
    proc = subprocess.run(
        [sys.executable, "-m", "flake8", "--jobs=1", str(sol)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return len(lines), f"{len(lines)} замечаний"


def score_c09_flake8() -> tuple[float, str]:
    """PEP8/flake8 для кода в src_solution."""
    n, note = run_flake8_src_solution()
    if n is None:
        return 0.0, note
    if n == 0:
        return 3.0, "0 замечаний flake8"
    if n <= 5:
        return 2.0, note
    return 0.0, note


def _cyclonedx_has_numpy(data: dict | None) -> bool:
    """Ищет в CycloneDX JSON упоминание numpy в компонентах/зависимостях."""

    def walk(obj: object) -> bool:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("name", "bom-ref", "ref", "purl") and isinstance(v, str):
                    if "numpy" in v.lower():
                        return True
                if walk(v):
                    return True
        elif isinstance(obj, list):
            for item in obj:
                if walk(item):
                    return True
        return False

    return walk(data) if data else False


def _cyclonedx_looks_valid(data: dict | None) -> bool:
    if not data or not isinstance(data, dict):
        return False
    return "components" in data or data.get("bomFormat") == "CycloneDX" or "metadata" in data


def score_c14_numpy_sbom_split() -> tuple[float, str]:
    """
    Размещение numpy в SBOM решения, макс. 3:
    0 — numpy в SBOM_TCB; 3 — только в SBOM_OTHER и оба файла валидны; 1–2 — промежуточные.
    """
    tcb_path = ROOT / "src_solution" / "sbom" / "SBOM_TCB.cdx.json"
    other_path = ROOT / "src_solution" / "sbom" / "SBOM_OTHER.cdx.json"

    def load_json(p: Path) -> dict | None:
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return None

    tcb = load_json(tcb_path)
    other = load_json(other_path)

    if tcb is None and other is None:
        return 1.0, "нет SBOM в src_solution/sbom"

    numpy_in_tcb = _cyclonedx_has_numpy(tcb)
    numpy_in_other = _cyclonedx_has_numpy(other)

    if numpy_in_tcb:
        return 0.0, "numpy в SBOM_TCB"
    if numpy_in_other:
        if _cyclonedx_looks_valid(tcb) and _cyclonedx_looks_valid(other):
            return 3.0, "numpy только в SBOM_OTHER, SBOM валидны"
        return 2.0, "numpy только в SBOM_OTHER"
    if _cyclonedx_looks_valid(tcb) and _cyclonedx_looks_valid(other):
        return 2.0, "numpy не в SBOM, файлы присутствуют"
    return 1.0, "numpy не в SBOM"


def score_c13_security_tests_section_solution_md() -> tuple[float, str]:
    """Раздел о тестах безопасности в src_solution/docs/solution.md."""
    p = ROOT / "src_solution" / "docs" / "solution.md"
    if not p.is_file():
        return 0.0, "нет src_solution/docs/solution.md"
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return 0.0, str(e)

    lower = txt.lower()
    has_section = ("результаты тестов безопасности" in lower) or (
        "тесты безопасности" in lower
    )
    path_link = bool(
        re.search(r"`src_solution/[^`\s]+`", txt)
        or re.search(r"\[[^\]]+\]\([^)]*src_solution[^)]*\)", txt)
        or re.search(r"src_solution/[^\s\)]+", txt)
    )
    n_paths = len(re.findall(r"src_solution/[^\s\)`]+", txt))
    if not has_section:
        return 0.0, "нет раздела по тестам безопасности в solution.md"
    if n_paths >= 3:
        return 3.0, f"раздел есть, явные пути ({n_paths})"
    if path_link:
        return 2.0, "раздел есть, есть путь/ссылка src_solution/"
    return 1.0, "раздел есть, но без явных путей к src_solution"


HEAVY_REQUIREMENT_PACKAGES = {"numpy", "fastapi"}


def _extract_requirement_name(line: str) -> str:
    """Извлекает имя пакета из строки requirements (без версий/маркеров)."""
    cleaned = line.strip().split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    # extras и маркеры не учитываем: fastapi[all]>=0.111; python_version>="3.11"
    name = re.split(r"[<>=!~;\[\s]", cleaned, maxsplit=1)[0].strip().lower()
    return name


def score_c11_dependencies() -> tuple[float, str]:
    """C11: пустой requirements.txt допустим, если зависимости вынесены в other."""
    sol_req = ROOT / "src_solution" / "requirements.txt"
    sol_py = ROOT / "src_solution" / "pyproject.toml"
    if not sol_req.is_file() and not sol_py.is_file():
        return 0.0, "нет requirements.txt / pyproject.toml"

    if sol_req.is_file():
        body = sol_req.read_text(encoding="utf-8", errors="replace").strip()
        lines = [ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        req_names = {_extract_requirement_name(ln) for ln in lines}
        req_names.discard("")
        other_req = ROOT / "src_solution" / "requirements-other.txt"
        n_ot = 0
        if other_req.is_file():
            ob = other_req.read_text(encoding="utf-8", errors="replace").strip()
            n_ot = len([ln for ln in ob.splitlines() if ln.strip() and not ln.strip().startswith("#")])
        if not lines:
            if n_ot:
                return 3.0, f"requirements.txt пустой, {n_ot} зависимостей только в requirements-other.txt"
            return 1.0, "requirements.txt пустой"
        heavy_found = sorted(req_names & HEAVY_REQUIREMENT_PACKAGES)
        if heavy_found:
            return 0.0, f"тяжёлые зависимости в requirements.txt: {', '.join(heavy_found)}"
        lab = (
            f"{len(lines)} в requirements.txt"
            + (f", +{n_ot} в requirements-other.txt" if n_ot else "")
        )
        if len(lines) == 1 and not n_ot:
            return 2.0, "одна зависимость"
        return 3.0, lab

    body = sol_py.read_text(encoding="utf-8", errors="replace")
    low_body = body.lower()
    if any(pkg in low_body for pkg in HEAVY_REQUIREMENT_PACKAGES):
        return 0.0, "тяжёлые зависимости в pyproject.toml"
    if len(body.strip()) < 20:
        return 1.0, "pyproject.toml почти пуст"
    if "[project]" in body or "[tool.poetry" in body:
        return 3.0, "pyproject с секцией проекта"
    return 2.0, "pyproject.toml без явной секции зависимостей"


def _solution_md_candidate():
    """Приоритет: отчёт участника ``src_solution/docs``, затем шаблон ``src_starting_point/docs``, указатель ``docs``."""
    p_sol = ROOT / "src_solution" / "docs" / "solution.md"
    if p_sol.is_file():
        return p_sol, str(p_sol.relative_to(ROOT))
    p_sp = ROOT / "src_starting_point" / "docs" / "solution.md"
    if p_sp.is_file():
        return p_sp, str(p_sp.relative_to(ROOT))
    p_docs = ROOT / "docs" / "solution.md"
    if p_docs.is_file():
        return p_docs, str(p_docs.relative_to(ROOT))
    return None, ""


def score_c17_solution_md() -> tuple[float, str]:
    """Наличие и полнота отчёта solution.md (эвристика по разделам).

    Если нет канонического файла ``src_solution/docs/solution.md``, применяется ограничение по баллам
    даже для развёрнутого fallback (шаблон / указатель в корне).
    """
    canonical_md = ROOT / "src_solution" / "docs" / "solution.md"
    md_path, _label = _solution_md_candidate()
    if md_path is None:
        return (
            0.0,
            "нет файла решения ни в src_solution/docs/solution.md, ни в src_starting_point/docs, ни в docs/",
        )
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return 0.0, str(e)
    lower = text.lower()
    if len(lower.strip()) < 50:
        return 0.0, "пусто или слишком кратко"

    has_arch = any(
        k in lower
        for k in (
            "архитектур",
            "компонент",
            "модуль",
            "abu",
            "двб",
            "разделен",
            "монитор",
        )
    )
    has_pol = "политик" in lower or ("цел" in lower and "безопас" in lower)
    has_e2e = "сквозн" in lower or "e2e" in lower or ("цр" in lower and "абу" in lower)
    has_sec = ("безопасност" in lower and "тест" in lower) or "tests/security" in lower
    has_cert = "сертификат" in lower or "сертификац" in lower
    has_diag = any(
        k in lower
        for k in (
            "диаграмм",
            "diagram",
            "mermaid",
            "plantuml",
            "![",
            ".png",
            ".svg",
        )
    )

    def finalize(score: float, note: str) -> tuple[float, str]:
        if not canonical_md.is_file() and score > 2.0:
            return min(score, 2.0), (
                note
                + " — отчёт не в `src_solution/docs/solution.md`; по регламенту не более 2 балла по C17"
            )
        return score, note

    if not has_arch:
        return 0.0, "нет описания архитектуры"
    if not ((has_e2e or has_sec) or has_cert):
        return 0.0, "нет результатов тестов/сертификации"

    core = has_arch and has_pol and has_e2e and has_sec and has_cert
    if core and has_diag:
        return finalize(
            3.0,
            "архитектура, политики, сквозные и security-тесты, сертификация, диаграммы",
        )
    if core and not has_diag:
        return 1.0, "нет архитектурных диаграмм (остальное есть)"
    missing: list[str] = []
    if not has_e2e:
        missing.append("сквозные тесты")
    if not has_sec:
        missing.append("тесты безопасности")
    if not has_cert:
        missing.append("сертификация")
    if len(missing) == 1 and has_arch and has_pol:
        return 2.0, f"не хватает: {missing[0]}"
    return 1.0, "частично"


def _count_loc(path: Path) -> int:
    """Подсчёт LOC без пустых строк и комментариев."""
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    total = 0
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        total += 1
    return total


def score_c23_tcb_domain_size() -> tuple[float, str]:
    """Оценка размера доменов ДВБ по наибольшему LOC одного домена."""
    tcb_root = ROOT / "src_solution" / "abu" / "tcb"
    if not tcb_root.is_dir():
        return 0.0, "нет src_solution/abu/tcb"
    domain_loc: dict[str, int] = {}
    for py in tcb_root.rglob("*.py"):
        if not py.is_file():
            continue
        rel = py.relative_to(tcb_root)
        if rel.parts and rel.parts[0] == "sys":
            dom = "tcb_sys"
        elif py.stem.startswith("domain_"):
            dom = py.stem.removeprefix("domain_")
        elif len(rel.parts) >= 2:
            dom = rel.parts[0]
        else:
            dom = py.stem
        domain_loc[dom] = domain_loc.get(dom, 0) + _count_loc(py)
    if not domain_loc:
        return 0.0, "нет python-кода доменов в tcb"
    max_dom, max_loc = max(domain_loc.items(), key=lambda item: item[1])
    if max_loc > 300:
        return 0.0, f"максимум {max_dom}={max_loc} LOC (>300)"
    if max_loc >= 200:
        return 1.0, f"максимум {max_dom}={max_loc} LOC (200-300)"
    if max_loc >= 100:
        return 2.0, f"максимум {max_dom}={max_loc} LOC (100-200)"
    return 3.0, f"максимум {max_dom}={max_loc} LOC (<100)"


def score_c24_tcb_interface_count() -> tuple[float, str]:
    """Оценка числа разрешающих IPC-политик для доменов ДВБ."""
    policies = ROOT / "src_solution" / "abu" / "tcb" / "sys" / "ipc_policies.json"
    if not policies.is_file():
        return 0.0, "нет src_solution/abu/tcb/sys/ipc_policies.json"
    try:
        raw = json.loads(policies.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return 0.0, "политики невалидны"

    allows = raw.get("allows") or []
    tcb_edges: dict[str, int] = {}
    for ent in allows:
        if not isinstance(ent, dict):
            continue
        src = str(ent.get("from") or "").strip()
        dst = str(ent.get("to") or "").strip()
        if src.startswith("tcb_"):
            tcb_edges[src] = tcb_edges.get(src, 0) + 1
        if dst.startswith("tcb_"):
            tcb_edges[dst] = tcb_edges.get(dst, 0) + 1
    if not tcb_edges:
        return 0.0, "нет разрешающих политик для tcb-доменов"

    max_dom, max_edges = max(tcb_edges.items(), key=lambda item: item[1])
    if max_edges >= 5:
        return 0.0, f"максимум {max_dom}={max_edges} политик (>=5)"
    if max_edges == 4:
        return 1.0, f"максимум {max_dom}={max_edges} политики"
    if max_edges == 3:
        return 2.0, f"максимум {max_dom}={max_edges} политики"
    if max_edges in (1, 2):
        return 3.0, f"максимум {max_dom}={max_edges} политики"
    return 0.0, f"максимум {max_dom}={max_edges} политик"


def score_c25_security_monitor(monitor_cov_pct: float | None, pytest_skipped: bool) -> tuple[float, str]:
    """Наличие monitor + security-тестов + покрытие monitor-кода."""
    py_sol, blob = _src_solution_snapshot()
    lower = blob.lower()
    has_monitor = any("security_monitor" in str(p).lower() for p in py_sol) or (
        "security_monitor" in lower
    )
    if not has_monitor:
        return 0.0, "security_monitor отсутствует"

    sec_tests = 0
    sol_tests = ROOT / "src_solution" / "tests"
    if sol_tests.is_dir():
        for tp in sol_tests.rglob("test_*.py"):
            if not tp.is_file():
                continue
            try:
                t = tp.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
            if "pytest.mark.security" in t or "security_monitor" in t:
                sec_tests += 1
    if sec_tests == 0:
        return 1.0, "monitor есть, но нет security-тестов в src_solution/tests"
    if pytest_skipped:
        return 2.0, f"monitor и security-тесты есть ({sec_tests}), но pytest не запускался"
    if monitor_cov_pct is None:
        return 2.0, f"monitor и security-тесты есть ({sec_tests}), но нет данных покрытия"
    if monitor_cov_pct < 60.0:
        return 2.0, f"coverage security_monitor={monitor_cov_pct:.1f}% (<60%)"
    return 3.0, f"coverage security_monitor={monitor_cov_pct:.1f}% (>=60%)"


def criterion_table(
    pytest_rc: int | None,
    tcb_cov_pct: float | None,
    monitor_cov_pct: float | None,
    *,
    cert_attempted: bool,
    cert_prepare_ok: bool,
    cert_info: dict[str, Any],
) -> list[tuple[str, float, str]]:
    """
    25 критериев; значение 0..3.
    pytest_rc: None если пропуск прогона.
    """
    rows: list[tuple[str, float, str]] = []

    def add(name: str, value: float, note: str, cap: float = 3.0) -> None:
        v = max(0.0, min(cap, float(value)))
        rows.append((name, v, note))

    pytest_skipped = pytest_rc is None
    e2e_exists = E2E_TEST_PATH.is_file()

    # C01
    if pytest_skipped:
        add(
            "C01: Все тесты репозитория (включая тесты решения) завершаются успешно",
            0.0,
            "пропуск (--no-pytest)",
        )
    else:
        add(
            "C01: Все тесты репозитория (включая тесты решения) завершаются успешно",
            3.0 if pytest_rc == 0 else 0.0,
            "OK" if pytest_rc == 0 else f"exit {pytest_rc}",
        )

    # C02
    sol_test_files = _solution_test_files_in_src_solution_tests()
    misplaced_tests = _misplaced_solution_test_files()
    n_sol = len(sol_test_files)
    n_mis = len(misplaced_tests)
    if n_sol == 0:
        c02 = 0.0
        n02 = "нет тестов в src_solution/tests"
    elif n_mis >= 4:
        c02 = 1.0
        n02 = f"в src_solution/tests: {n_sol}, вне каталога: {n_mis}"
    elif n_mis >= 1:
        c02 = 2.0
        n02 = f"в src_solution/tests: {n_sol}, есть тесты вне каталога: {n_mis}"
    else:
        c02 = 3.0
        n02 = f"все тесты решения ({n_sol}) находятся в src_solution/tests/**"
    add(
        "C02: Все тесты решения находятся в подкаталогах src_solution/tests",
        c02,
        n02,
    )

    # C03
    if not _pytest_ini_has_security_marker():
        c03 = 0.0
        n03 = "нет pytest.ini или маркера security"
    else:
        mused = _security_marker_used_in_tests()
        if mused >= 3:
            c03 = 3.0
            n03 = f"маркер security используется ({mused} файлов)"
        elif mused >= 1:
            c03 = 2.0
            n03 = f"маркер security в тестах ({mused} файлов)"
        else:
            c03 = 1.0
            n03 = "pytest.ini с security, маркер не использован в тестах"
    add("C03: Маркер security в pytest.ini и использование в тестах", c03, n03)

    # C04
    nf = _count_event_log_related_tests()
    if nf <= 0:
        add("C04: Покрытие тестами event_log / журнал", 0.0, "нет релевантных тестовых функций")
    elif nf >= 4:
        add("C04: Покрытие тестами event_log / журнал", 3.0, f"{nf} тестовых функций")
    elif nf >= 2:
        add("C04: Покрытие тестами event_log / журнал", 2.0, f"{nf} тестовых функций")
    else:
        add("C04: Покрытие тестами event_log / журнал", 1.0, f"{nf} тестовых функций")

    # C05
    sga = ROOT / "docs" / "examples" / "sga.json"
    if not sga.is_file():
        add("C05: Пример sga.json", 0.0, "нет docs/examples/sga.json")
    else:
        try:
            data = json.loads(sga.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            add("C05: Пример sga.json", 1.0, "файл не JSON")
        else:
            if isinstance(data, dict) and len(data) >= 2:
                add("C05: Пример sga.json", 3.0, "валидный JSON, несколько ключей")
            elif isinstance(data, dict) and data:
                add("C05: Пример sga.json", 2.0, "валидный JSON")
            else:
                add("C05: Пример sga.json", 1.0, "JSON минимальный")

    # C06
    tcb_e = ROOT / "src_starting_point" / "sbom" / "SBOM_TCB.cdx.json"
    oth_e = ROOT / "src_starting_point" / "sbom" / "SBOM_OTHER.cdx.json"
    if not tcb_e.is_file() or not oth_e.is_file():
        add("C06: SBOM TCB / OTHER в примерах", 0.0, "нет обоих файлов в src_starting_point/sbom/")
    else:
        try:
            jt = json.loads(tcb_e.read_text(encoding="utf-8", errors="replace"))
            jo = json.loads(oth_e.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            add("C06: SBOM TCB / OTHER в примерах", 1.0, "файлы не JSON")
        else:
            if _cyclonedx_looks_valid(jt) and _cyclonedx_looks_valid(jo):
                add("C06: SBOM TCB / OTHER в примерах", 3.0, "CycloneDX валиден")
            else:
                add("C06: SBOM TCB / OTHER в примерах", 2.0, "JSON без полной структуры CycloneDX")

    # C07
    cert_success = bool(cert_info.get("success")) if cert_info else False
    cert_hash_ok = cert_info.get("hash_ok") if cert_info else None
    cert_msg = str(cert_info.get("message") or "") if cert_info else ""
    if not cert_attempted:
        add(
            "C07: Успешное выполнение сертификации (пакет + ответ Регулятора)",
            0.0,
            "сертификация не запускалась (используйте --with-certification)",
        )
    elif not cert_prepare_ok:
        add(
            "C07: Успешное выполнение сертификации (пакет + ответ Регулятора)",
            0.0,
            "ошибка подготовки пакета решения",
        )
    elif not cert_success:
        tail = cert_msg[:120] if cert_msg else "Регулятор вернул отказ"
        add(
            "C07: Успешное выполнение сертификации (пакет + ответ Регулятора)",
            1.0,
            tail,
        )
    elif cert_hash_ok is False:
        add(
            "C07: Успешное выполнение сертификации (пакет + ответ Регулятора)",
            2.0,
            "сертификация успешна, но хэш сертификата не совпал",
        )
    else:
        add(
            "C07: Успешное выполнение сертификации (пакет + ответ Регулятора)",
            3.0,
            "сертификация успешна",
        )

    # C08
    scen_ok, scen_note = _e2e_matches_operational_scenario()
    if not e2e_exists:
        add(
            "C08: Сквозной автотест ЦР–АБУ (основной сценарий)",
            0.0,
            "нет test_e2e_abu_dm_scenario.py",
        )
    elif not scen_ok:
        add(
            "C08: Сквозной автотест ЦР–АБУ (основной сценарий)",
            1.0,
            scen_note,
        )
    elif pytest_skipped:
        add(
            "C08: Сквозной автотест ЦР–АБУ (основной сценарий)",
            2.0,
            "файл есть; пропуск pytest",
        )
    elif pytest_rc == 0:
        add(
            "C08: Сквозной автотест ЦР–АБУ (основной сценарий)",
            3.0,
            f"pytest OK; {scen_note}",
        )
    else:
        add("C08: Сквозной автотест ЦР–АБУ (основной сценарий)", 0.0, "pytest упал")

    c09, n09 = score_c09_flake8()
    add("C09: Оформление кода в src_solution (flake8, PEP8)", c09, n09)

    py_sol, blob_sol = _src_solution_snapshot()
    lower_sol = blob_sol.lower()

    # C10
    if not py_sol:
        add("C10: Решение: журнал событий / event_log в src_solution", 0.0, "нет .py в src_solution")
    elif any("event_log" in str(p).lower() for p in py_sol):
        add("C10: Решение: журнал событий / event_log в src_solution", 3.0, "модуль event_log в дереве")
    elif "event_log" in lower_sol:
        add("C10: Решение: журнал событий / event_log в src_solution", 2.0, "event_log в коде")
    else:
        add("C10: Решение: журнал событий / event_log в src_solution", 1.0, "есть код без event_log")

    c11, n11 = score_c11_dependencies()
    add("C11: Решение: зависимости (requirements / pyproject в src_solution)", c11, n11)

    # C12 — AST-импорты src_solution из tests/ и src_solution/tests/
    t_imp = _test_files_importing_src_solution()
    nt = len(t_imp)
    if nt >= 3:
        c12 = 3.0
    elif nt == 2:
        c12 = 2.0
    elif nt == 1:
        c12 = 1.0
    else:
        c12 = 0.0
    add(
        "C12: Тесты репозитория импортируют код из src_solution (AST)",
        c12,
        f"файлов с import src_solution: {nt}",
    )

    c13, n13 = score_c13_security_tests_section_solution_md()
    add("C13: Раздел тестов безопасности в src_solution/docs/solution.md", c13, n13)

    c14, n14 = score_c14_numpy_sbom_split()
    add("C14: numpy в SBOM решения (SBOM_TCB vs SBOM_OTHER)", c14, n14, cap=3.0)

    # C15
    t_both = _test_files_importing_event_log_and_src_solution()
    nb = len(t_both)
    if nb >= 2:
        c15 = 3.0
    elif nb == 1:
        c15 = 2.0
    else:
        c15 = 0.0
    add(
        "C15: Тесты: журнал event_log и решение (импорты из src_solution + event_log)",
        c15,
        f"файлов: {nb}",
    )

    c16, n16 = score_c16_tcb_coverage(tcb_cov_pct, pytest_skipped)
    add("C16: Покрытие ДВБ решения (src_solution/abu/tcb) тестами", c16, n16)

    c17, n17 = score_c17_solution_md()
    add("C17: Отчёт о решении (приоритет `src_solution/docs/solution.md`)", c17, n17)

    c18, c19, n18, n19 = score_c18_c19_solution(py_sol, blob_sol)
    add(
        "C18: security_monitor, policies в src_solution; тесты политик",
        c18,
        n18,
    )
    add(
        "C19: домены и монитор; разнесение по процессам (не только каталоги tcb/other)",
        c19,
        n19,
    )
    add(
        "C20: Стоимость сертификации — место в рейтинге (жюри: 3 / 2 / 1 / 0)",
        0.0,
        "автоматика 0; жюри после сравнения всех участников",
    )
    add(
        "C21: Экспертно — соответствие политик архитектуре АБУ (жюри)",
        0.0,
        "автоматика 0; заполняет жюри",
    )
    add(
        "C22: Экспертно — полнота отчёта и воспроизводимость (жюри)",
        0.0,
        "автоматика 0; заполняет жюри",
    )
    c23, n23 = score_c23_tcb_domain_size()
    add("C23: Размер доменов ДВБ (максимальный LOC одного домена)", c23, n23)

    c24, n24 = score_c24_tcb_interface_count()
    add("C24: Количество интерфейсов домена ДВБ (разрешающие IPC-политики)", c24, n24)

    c25, n25 = score_c25_security_monitor(monitor_cov_pct, pytest_skipped)
    add("C25: Наличие security_monitor, security-тесты и покрытие monitor-кода", c25, n25)

    assert len(rows) == 25, len(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Оценка прототипа по 25 критериям (макс. 3 за критерий).",
    )
    parser.add_argument("--no-pytest", action="store_true", help="Не запускать pytest")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_out",
        help="JSON в stdout",
    )
    parser.add_argument(
        "--write-detailed",
        metavar="PATH",
        help=(
            "записать подробный Markdown по критериям "
            "(таблица и итог)"
        ),
    )
    parser.add_argument(
        "--with-certification",
        action="store_true",
        help=(
            "после оценки: prepare_certification_bundle_solution + запрос Регулятора"
        ),
    )
    args = parser.parse_args()

    script_here = Path(__file__).resolve()
    participant = os.environ.get("CONTEST_PARTICIPANT_SRC_SOLUTION")
    if participant:
        sys.path.insert(0, str(script_here.parent))
        from contest_repo_merge import merge_organizer_with_participant

        organizer = Path(
            os.environ.get(
                "CONTEST_ORGANIZER_ROOT",
                str(script_here.parents[1]),
            ),
        )
        merge_organizer_with_participant(organizer, Path(participant))

    default_root = str(script_here.parents[1])
    root_eff = Path(os.environ.get("CONTEST_REPO_ROOT", default_root))
    _sync_eval_root_globals(root_eff)

    pytest_rc: int | None = None
    tcb_cov_pct: float | None = None
    monitor_cov_pct: float | None = None
    if not args.no_pytest:
        pytest_rc, tcb_cov_pct, monitor_cov_pct = run_pytest_with_tcb_coverage()

    cert_prep_error = ""
    cert_reg: dict[str, Any] = {}
    cert_block = ""
    prep_ok = False
    cert_attempted = bool(args.with_certification)
    if args.with_certification:
        sys.path.insert(0, str(script_here.parent))
        from regulator_certification import (
            format_certification_markdown,
            prepare_solution_bundle,
            request_certification,
        )

        prep_ok, cert_prep_error = prepare_solution_bundle(ROOT, sys.executable)
        if prep_ok:
            cert_reg = request_certification(ROOT)
        cert_block = format_certification_markdown(
            cert_reg,
            "" if prep_ok else cert_prep_error,
            repo_root=ROOT,
        )

    rows = criterion_table(
        pytest_rc,
        tcb_cov_pct,
        monitor_cov_pct,
        cert_attempted=cert_attempted,
        cert_prepare_ok=prep_ok,
        cert_info=cert_reg,
    )
    raw = sum(v for _, v, _ in rows)
    if args.write_detailed:
        sys.path.insert(0, str(script_here.parent))
        from evaluation_report_md import write_detailed_report

        write_detailed_report(
            Path(args.write_detailed),
            rows,
            raw,
            title="Подробная оценка по критериям",
            certification_block=cert_block if args.with_certification else "",
        )

    extra_json: dict[str, object] = {
        "eval_root": str(ROOT.resolve()),
        "participant_overlay": participant,
    }
    if args.with_certification:
        extra_json["certification"] = {
            "prepare_ok": prep_ok,
            "prepare_error": cert_prep_error or None,
            "regulator": cert_reg,
        }

    if args.json_out:
        payload = {
            "raw_sum": raw,
            "raw_max": RAW_MAX,
            "criteria": [
                {"name": n, "score": v, "note": t} for n, v, t in rows
            ],
            **extra_json,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.exit(0)

    print(
        f"Оценка по критериям (0–3 за критерий; сумма до {RAW_MAX:.0f}), "
        f"ROOT={ROOT}:\n",
    )
    for name, v, note in rows:
        print(f"  {name}: {v:.1f}  ({note})")
    print(f"\nСумма (raw): {raw:.1f} / {RAW_MAX:.0f}")
    if args.with_certification:
        if not prep_ok and cert_prep_error:
            print(
                f"\nСертификация: не удалось собрать пакет решения ({cert_prep_error[:400]}…)",
                file=sys.stderr,
            )
        elif prep_ok:
            cost = float(cert_reg.get("estimated_cost") or 0.0)
            ok_req = cert_reg.get("success")
            print(f"\nСертификация (ответ Регулятора): успех={ok_req}, стоимость≈{cost:.2f} усл. ед.")
    sys.exit(0)


if __name__ == "__main__":
    main()
