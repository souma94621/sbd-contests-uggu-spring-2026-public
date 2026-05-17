"""Песочница: изолированные зависимости (pip install -t) и pytest с покрытием по коду АБУ."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from regulator.tcb_metrics import abu_has_security_domain_split


@dataclass
class PytestCovResult:
    ok: bool
    coverage_total: float
    coverage_tcb: float
    coverage_other: float
    log: str


def _parse_coverage_table_line(norm: str) -> tuple[str, int, int] | None:
    """Строка ``abu/...py  N  M  P% …`` — после процентов возможен список пропущенных строк."""
    parts = norm.split()
    if len(parts) < 4:
        return None
    pct_i = None
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].endswith("%"):
            pct_i = i
            break
    if pct_i is None or pct_i < 3:
        return None
    try:
        miss = int(parts[pct_i - 1])
        stmts = int(parts[pct_i - 2])
    except ValueError:
        return None
    fn = parts[0].replace("\\", "/")
    if not (fn.endswith(".py") and fn.startswith("abu/")):
        return None
    return fn, stmts, miss


def run_pytest_with_coverage(
    source_dir: Path,
    tests_subdir: str = "tests",
    cov_fail_under: float | None = None,
    extra_pytest_args: list[str] | None = None,
) -> PytestCovResult:
    """
    Запускает pytest с ``--cov=abu`` (единый пакет; подпакеты ``abu.tcb``/``abu.other``
    не используются — иначе coverage может не собрать данные при importlib).

    Проценты **TCB** и **OTHER** вычисляются по строкам отчёта ``term-missing`` для
    файлов под ``abu/tcb/`` и ``abu/other/``. Плоский ``abu`` без этих каталогов —
    все файлы идут в метрику TCB, OTHER = 100%.
    """
    req = source_dir / "requirements.txt"
    if not req.is_file():
        return PytestCovResult(False, 0.0, 0.0, 0.0, "нет requirements.txt в пакете")

    abu = source_dir / "abu"
    has_split = abu_has_security_domain_split(abu) if abu.is_dir() else False

    tmp = Path(tempfile.mkdtemp(prefix="reg_sandbox_"))
    lib = tmp / "pylib"
    lib.mkdir(parents=True)
    try:
        inst = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-q",
                "-r",
                str(req),
                "-t",
                str(lib),
                "pytest",
                "pytest-cov",
            ],
            capture_output=True,
            text=True,
        )
        if inst.returncode != 0:
            return PytestCovResult(
                False, 0.0, 0.0, 0.0, inst.stdout + inst.stderr,
            )

        other_req = source_dir / "requirements-other.txt"
        if other_req.is_file():
            inst2 = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-q",
                    "-r",
                    str(other_req),
                    "-t",
                    str(lib),
                ],
                capture_output=True,
                text=True,
            )
            if inst2.returncode != 0:
                return PytestCovResult(
                    False, 0.0, 0.0, 0.0, inst2.stdout + inst2.stderr,
                )

        tests_path = source_dir / tests_subdir
        env = os.environ.copy()
        sep = os.pathsep
        env["PYTHONPATH"] = sep.join([str(source_dir), str(lib)])

        if cov_fail_under is None:
            cov_fu = os.environ.get("REGULATOR_COV_FAIL_UNDER", "0").strip()
        else:
            cov_fu = str(cov_fail_under)

        cmd: list[str] = [
            sys.executable,
            "-m",
            "pytest",
            str(tests_path),
            "-q",
            "--import-mode=importlib",
            "--cov=abu",
            "--cov-report=term-missing",
        ]
        if cov_fu and cov_fu != "0":
            cmd.append(f"--cov-fail-under={cov_fu}")

        cmd.extend(
            [
                "--rootdir",
                str(source_dir),
                "-o",
                "testpaths=",
                "-o",
                "pythonpath=.",
            ],
        )
        if extra_pytest_args:
            cmd.extend(extra_pytest_args)
        pr = subprocess.run(
            cmd,
            cwd=str(source_dir),
            capture_output=True,
            text=True,
            env=env,
        )
        log = pr.stdout + "\n" + pr.stderr
        tcb_pct, other_pct = _aggregate_tcb_other_percent(
            log,
            flat_legacy=not has_split,
        )
        total_pct = _parse_total_coverage_percent(log)
        ok = pr.returncode == 0
        return PytestCovResult(
            ok=ok,
            coverage_total=total_pct,
            coverage_tcb=tcb_pct,
            coverage_other=other_pct,
            log=log,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parse_total_coverage_percent(log: str) -> float:
    for raw in log.splitlines():
        line = raw.strip().replace("\\", "/")
        if line.startswith("TOTAL"):
            parts = line.split()
            for p in parts:
                if p.endswith("%"):
                    try:
                        return float(p.rstrip("%"))
                    except ValueError:
                        continue
    return 0.0


def _aggregate_tcb_other_percent(log: str, *, flat_legacy: bool) -> tuple[float, float]:
    """Суммируем Stmt/Miss для ``abu/tcb``, ``abu/other`` или плоского ``abu``."""
    ts = tm = os_ = om_ = 0
    for raw in log.splitlines():
        norm = raw.replace("\\", "/").strip()
        parsed = _parse_coverage_table_line(norm)
        if parsed is None:
            continue
        fn, st, mi = parsed

        fn_n = "/" + fn

        if flat_legacy:
            if "/tcb/" not in fn_n and "/other/" not in fn_n:
                ts += st
                tm += mi
            continue

        if "/tcb/" in fn_n or fn.startswith("abu/tcb/"):
            ts += st
            tm += mi
        elif "/other/" in fn_n or fn.startswith("abu/other/"):
            os_ += st
            om_ += mi

    def pct(stmts: int, miss: int) -> float:
        if stmts <= 0:
            return 100.0
        return round(100.0 * float(stmts - miss) / float(stmts), 2)

    tc = pct(ts, tm)
    oc = pct(os_, om_)
    if flat_legacy:
        return tc, 100.0
    return tc, oc


def run_security_tests_coverage(
    source_dir: Path,
    fail_under: float | None = None,
) -> PytestCovResult:
    sec = source_dir / "tests" / "security"
    if not sec.is_dir():
        return PytestCovResult(
            True, 100.0, 100.0, 100.0, "tests/security отсутствует, пропуск",
        )

    fu = fail_under
    if fu is None:
        fu = float(os.environ.get("REGULATOR_SECURITY_COV_FAIL_UNDER", "70"))

    return run_pytest_with_coverage(
        source_dir,
        tests_subdir="tests/security",
        cov_fail_under=fu,
    )
