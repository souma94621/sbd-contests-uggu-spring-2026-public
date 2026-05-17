"""Метрики исходного кода доверенной базы (ДВБ): строки и цикломатическая сложность."""

from __future__ import annotations

import ast
import fnmatch
from pathlib import Path
from typing import Any, Iterable


def iter_python_files(package_root: Path) -> list[Path]:
    """Все *.py под каталогом пакета, без __pycache__."""
    if not package_root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(package_root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        out.append(p)
    return out


def count_physical_loc(paths: Iterable[Path]) -> int:
    """Физическое число строк в перечисленных файлах."""
    total = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total += len(text.splitlines())
    return total


def _cyclomatic_of_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """
    Цикломатическая сложность одной функции (Маккейб): база 1 + точки ветвления.

    Вложенные определения функций не учитываются внутри внешней (они считаются отдельно).
    """

    class V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.score = 1

        def visit_If(self, n: ast.If) -> None:
            self.score += 1
            self.generic_visit(n)

        def visit_While(self, n: ast.While) -> None:
            self.score += 1
            self.generic_visit(n)

        def visit_For(self, n: ast.For) -> None:
            self.score += 1
            self.generic_visit(n)

        def visit_AsyncFor(self, n: ast.AsyncFor) -> None:
            self.score += 1
            self.generic_visit(n)

        def visit_ExceptHandler(self, n: ast.ExceptHandler) -> None:
            self.score += 1
            self.generic_visit(n)

        def visit_With(self, n: ast.With) -> None:
            self.score += 1
            self.generic_visit(n)

        def visit_Assert(self, n: ast.Assert) -> None:
            self.score += 1
            self.generic_visit(n)

        def visit_BoolOp(self, n: ast.BoolOp) -> None:
            self.score += len(n.values) - 1
            self.generic_visit(n)

        def visit_FunctionDef(self, n: ast.FunctionDef) -> None:
            return  # вложенные функции — отдельные сущности

        def visit_AsyncFunctionDef(self, n: ast.AsyncFunctionDef) -> None:
            return

    v = V()
    for stmt in node.body:
        v.visit(stmt)
    return v.score


def sum_cyclomatic_complexity(paths: Iterable[Path]) -> int:
    """
    Сумма цикломатических сложностей по всем функциям и методам в файлах пакета.
    """
    total = 0
    for path in paths:
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total += _cyclomatic_of_function(node)
    return total


def abu_has_security_domain_split(abu_package_root: Path) -> bool:
    """True, если в пакете явно разведены домены ``abu/tcb`` и ``abu/other`` (поддеревья)."""
    if not abu_package_root.is_dir():
        return False
    return (abu_package_root / "tcb").is_dir() and (abu_package_root / "other").is_dir()


def compute_tcb_source_metrics(abu_package_root: Path) -> tuple[int, int]:
    """
    Возвращает (число строк физических, сумма цикломатики) для учёта в стоимости как **ДВБ**.

    Если разделения **нет** (нет обоих каталогов ``tcb`` и ``other`` под ``abu``), Регулятор
    считает **весь** код под ``abu`` входящим в цели безопасности (единый условный TCB для
    стоимости и того же трактования, что покрытие ``coverage_tcb_percent`` без отдельного other).

    Если разделение **есть**, метрики считаются **только** по дереву ``abu/tcb`` (доверенная
    база для целей безопасности); код под ``abu/other`` не входит в эти суммы для стоимости.
    Покрытие по строкам для ``abu/other`` по-прежнему отражается в ``coverage_other_percent``.
    """
    metrics_root = abu_package_root
    if abu_has_security_domain_split(abu_package_root):
        metrics_root = abu_package_root / "tcb"

    py_files = iter_python_files(metrics_root)
    loc = count_physical_loc(py_files)
    cc = sum_cyclomatic_complexity(py_files)
    return loc, cc


def _rel_posix_from_root(root: Path, path: Path) -> str:
    rel = path.resolve().relative_to(root.resolve())
    return rel.as_posix()


def partition_tcb_into_domains(
    metrics_root: Path,
    spec: dict[str, Any],
) -> tuple[list[tuple[str, int, int]], list[str]]:
    """
    Разбивает метрики Python-файлов под ``metrics_root`` на домены по ``spec`` (``security_cost_domains``).

    Порядок записей в ``domains`` важен: первое совпавшее глоб-правило захватывает файл.
    Неназначенные ``*.py`` попадают в домен ``_residual``.

    Возвращает список ``(domain_id, loc, cc)`` и список предупреждений (пересечения невозможны).
    """
    domains_cfg = list(spec.get("domains") or [])
    warnings: list[str] = []

    py_files = iter_python_files(metrics_root)
    resolved_root = metrics_root.resolve()
    assigned: dict[Path, str] = {}

    def try_match(pat: str, rel: str) -> bool:
        rel_norm = rel
        patterns = (
            pat,
            "**/" + pat,
            "**/" + pat.lstrip("*"),
        )
        for p in patterns:
            if fnmatch.fnmatch(rel_norm, p) or fnmatch.fnmatch(rel_norm, p.strip("/")):
                return True
        head, _, tail = rel_norm.rpartition("/")
        if tail and fnmatch.fnmatch(tail, pat):
            return True
        return fnmatch.fnmatch(rel_norm.split("/")[-1], pat)

    for blk in domains_cfg:
        if not isinstance(blk, dict):
            continue
        dom_id = str(blk.get("id") or "").strip()
        globs = [str(g) for g in (blk.get("globs") or [])]
        if not dom_id:
            warnings.append("пропуск записи домена без id")
            continue
        if dom_id == "_residual":
            warnings.append("домен _residual обрабатывается автоматически; запись во входной спецификации игнорируется")
            continue
        matched_any = False
        for path in py_files:
            if path in assigned:
                continue
            rel = _rel_posix_from_root(resolved_root, path)
            if not globs:
                continue
            for g in globs:
                if try_match(g.strip(), rel):
                    assigned[path] = dom_id
                    matched_any = True
                    break
        if globs and not matched_any:
            warnings.append(f"домен {dom_id!r}: ни один файл пока не сопоставлен glob-выражением")

    leftover: list[Path] = [p for p in py_files if p not in assigned]
    for path in leftover:
        assigned[path] = "_residual"

    buckets: dict[str, list[Path]] = {}
    for path, did in assigned.items():
        buckets.setdefault(did, []).append(path)

    rows: list[tuple[str, int, int]] = []
    for did in sorted(buckets.keys(), key=lambda x: (x != "_residual", x)):
        paths = buckets[did]
        loc = count_physical_loc(paths)
        cc = sum_cyclomatic_complexity(paths)
        rows.append((did, loc, cc))

    return rows, warnings
