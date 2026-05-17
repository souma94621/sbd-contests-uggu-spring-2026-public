"""Генерация подробного Markdown-отчёта по критериям C01–C25."""

from __future__ import annotations

import re
from pathlib import Path

RAW_MAX = 75.0


def criterion_max_display(name: str, score: float) -> tuple[float, str]:
    """Макс. баллов и пояснение для C20–C22 (автоматика 0)."""
    if re.match(r"^C2[0-2]:", name):
        return 3.0, "автоматическая часть 0; макс. заполняет жюри"
    return 3.0, ""


def parse_criterion_id(name: str) -> str:
    m = re.match(r"^(C\d\d)\s*:", name)
    return m.group(1) if m else ""


def detailed_markdown_lines(
    rows: list[tuple[str, float, str]],
    raw: float,
    title: str | None = None,
    certification_block: str = "",
) -> list[str]:
    out: list[str] = []
    if title:
        out.append("# " + title + "\n")
        out.append("")
    out.append("## Результаты по критериям\n")
    out.append("")
    out.append(
        "| ID критерия | формулировка | набрано баллов в решении | "
        "максимально баллов | почему такой результат |\n",
    )
    out.append("| --- | --- | ---: | ---: | --- |\n")
    for name, score, note in rows:
        cid = parse_criterion_id(name)
        rest = name.split(":", 1)[-1].strip() if ":" in name else name
        mx, mx_note = criterion_max_display(name, score)
        why = note
        if mx_note:
            why = f"{note}. {mx_note}" if note else mx_note
        line = "| {} | {} | {:g} | {:g} | {} |\n".format(
            cid or "—",
            rest.replace("|", "\\|"),
            score,
            mx,
            why.replace("|", "\\|").replace("\n", " "),
        )
        out.append(line)
    out.append("")
    out.append("## Итог автоматической проверки\n")
    out.append("")
    out.append(f"- **Сумма (raw):** {raw:g} / {RAW_MAX:g}\n")
    out.append("")
    if certification_block.strip():
        out.append(certification_block)
    return out


def write_detailed_report(
    path: Path,
    rows: list[tuple[str, float, str]],
    raw: float,
    title: str | None = None,
    certification_block: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = detailed_markdown_lines(
        rows,
        raw,
        title=title,
        certification_block=certification_block,
    )
    path.write_text("".join(lines), encoding="utf-8")
