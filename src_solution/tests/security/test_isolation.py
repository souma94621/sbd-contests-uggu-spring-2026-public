"""Тесты изоляции доменов. Критерии: C19, C25."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

_TCB_PATH = Path(__file__).parent.parent.parent / "abu" / "tcb"
_OTHER_PATH = Path(__file__).parent.parent.parent / "abu" / "other"


def _get_imports(filepath: Path) -> list[str]:
    """Извлечь все импорты из файла через AST."""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_tcb_does_not_import_other():
    """Ни один файл ДВБ не импортирует из other."""
    for py_file in _TCB_PATH.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        imports = _get_imports(py_file)
        for imp in imports:
            assert "other" not in imp, (
                f"{py_file.name} импортирует из other: {imp}"
            )


def test_tcb_files_exist():
    """Все ключевые файлы ДВБ существуют."""
    required = [
        "event_log.py",
        "safety.py",
        "limits.py",
        "security_monitor.py",
        "ipc_policies.json",
    ]
    for name in required:
        assert (_TCB_PATH / name).is_file(), f"Нет файла: {name}"


def test_other_files_exist():
    """Все ключевые файлы other существуют."""
    required = ["ai_engine.py", "app.py"]
    for name in required:
        assert (_OTHER_PATH / name).is_file(), f"Нет файла: {name}"


def test_numpy_not_in_tcb():
    """numpy не импортируется в ДВБ."""
    for py_file in _TCB_PATH.glob("*.py"):
        imports = _get_imports(py_file)
        assert "numpy" not in imports, (
            f"{py_file.name} импортирует numpy — он должен быть только в other"
        )