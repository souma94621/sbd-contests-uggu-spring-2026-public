"""Сборка полного дерева проверки: эталон репозитория + дерево ``src_solution`` участника."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import time
from pathlib import Path

_COPY_SKIP_DIRS = frozenset({
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tmp_eval",
    "evaluation",
})
_STALE_MERGE_DIR_TTL_SEC = 24 * 60 * 60


def _ignore_copy(path: str, names: list[str]) -> list[str]:
    skipped: list[str] = []
    for n in names:
        if n in _COPY_SKIP_DIRS:
            skipped.append(n)
        elif n.startswith(".venv"):
            skipped.append(n)
    return skipped


def _cleanup_stale_merge_dirs(merge_root: Path) -> None:
    """Удаляет устаревшие merge-деревья, оставшиеся после аварийных прерываний."""
    now = time.time()
    try:
        entries = list(merge_root.iterdir())
    except OSError:
        return
    for entry in entries:
        if not entry.is_dir():
            continue
        if not entry.name.startswith("contest_eval_"):
            continue
        try:
            age = now - entry.stat().st_mtime
        except OSError:
            continue
        if age > _STALE_MERGE_DIR_TTL_SEC:
            shutil.rmtree(entry, ignore_errors=True)


def normalize_participant_overlay(overlay: Path) -> Path:
    """Путь к каталогу с содержимым src_solution решения участника."""
    o = overlay.resolve()
    inner = o / "src_solution"
    if inner.is_dir() and (o / "pytest.ini").is_file():
        return inner
    if inner.is_dir() and not (o / "abu").exists() and not (o / "pytest.ini").is_file():
        return inner
    if inner.is_dir():
        return inner
    return o


def merge_organizer_with_participant(
    organizer_root: Path,
    participant_overlay: Path,
) -> Path:
    """Копирует эталон во временный каталог и подменяет ``src_solution``."""
    organ = organizer_root.resolve()
    part = normalize_participant_overlay(participant_overlay)
    if not part.is_dir():
        raise ValueError(f"Нет каталога участника: {participant_overlay}")

    # Временный merged-root по умолчанию внутри дерева организатора;
    # при необходимости выносится через CONTEST_MERGE_PARENT (например, в CI scratch).
    merge_parent = os.environ.get("CONTEST_MERGE_PARENT", "").strip()
    merge_tmp_root = Path(merge_parent).resolve() if merge_parent else (organ / ".tmp_eval")
    merge_tmp_root.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_merge_dirs(merge_tmp_root)
    tmp = Path(tempfile.mkdtemp(prefix="contest_eval_", dir=str(merge_tmp_root)))
    try:
        shutil.copytree(
            organ,
            tmp,
            symlinks=False,
            ignore=_ignore_copy,
            dirs_exist_ok=True,
        )
    except OSError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f"Не удалось скопировать эталон из {organ}: {exc}") from exc

    target = tmp / "src_solution"
    if target.is_dir():
        shutil.rmtree(target)
    try:
        shutil.copytree(part, target, symlinks=False, dirs_exist_ok=False)
    except OSError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f"Не удалось скопировать src_solution из {part}: {exc}") from exc

    def _cleanup() -> None:
        shutil.rmtree(tmp, ignore_errors=True)

    atexit.register(_cleanup)
    os.environ["CONTEST_REPO_ROOT"] = str(tmp.resolve())
    return tmp.resolve()
