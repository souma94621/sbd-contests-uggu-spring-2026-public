"""Подготовка пакета и запрос сертификации к локальному API Регулятора."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import json


def prepare_solution_bundle(repo_root: Path, python_exe: str | None = None) -> tuple[bool, str]:
    """Собирает ``artifacts/abu_certification_bundle.tar.gz`` из дерева решения."""
    repo_root = repo_root.resolve()
    script = repo_root / "scripts" / "prepare_certification_bundle_solution.sh"
    if not script.is_file():
        return False, "нет scripts/prepare_certification_bundle_solution.sh"
    env = os.environ.copy()
    py = python_exe or sys.executable
    env["CONTEST_REPO_ROOT"] = str(repo_root)
    env["CONTEST_PYTHON"] = py
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    tail = ""
    if proc.stderr:
        tail += proc.stderr.strip()
    if proc.stdout:
        tail += ("\n" if tail else "") + proc.stdout.strip()
    if proc.returncode != 0:
        return False, (tail or f"код выхода {proc.returncode}")[-4000:]
    return True, ""


def request_certification(
    repo_root: Path,
) -> dict[str, Any]:
    """
    Отправляет готовый архив на /api/v1/certification/requests.
    Использует external_systems/regulator из того же дерева, что repo_root.
    """
    repo_root = repo_root.resolve()
    bundle = repo_root / "artifacts" / "abu_certification_bundle.tar.gz"
    out: dict[str, Any] = {
        "success": False,
        "estimated_cost": 0.0,
        "certificate_id": None,
        "tcb_lines_of_code": 0,
        "tcb_cyclomatic_sum": 0,
        "message": None,
        "hash_ok": None,
    }
    if not bundle.is_file():
        out["message"] = "нет artifacts/abu_certification_bundle.tar.gz"
        return out

    expected_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
    reg = repo_root / "external_systems" / "regulator"
    if not reg.is_dir():
        out["message"] = "нет external_systems/regulator"
        return out

    sys.path.insert(0, str(reg))
    from fastapi.testclient import TestClient
    from regulator.main import app

    client = TestClient(app)
    dev = os.environ.get("CERT_DEVELOPER_COMPANY", "Локальная разработка")
    resp = client.post(
        "/api/v1/certification/requests",
        json={
            "bundle_path": str(bundle.resolve()),
            "developer_company": dev,
        },
    )
    data = resp.json()
    out["success"] = bool(data.get("success", False))
    out["estimated_cost"] = float(data.get("estimated_cost", 0.0) or 0.0)
    out["certificate_id"] = data.get("certificate_id")
    out["tcb_lines_of_code"] = int(data.get("tcb_lines_of_code", 0) or 0)
    out["tcb_cyclomatic_sum"] = int(data.get("tcb_cyclomatic_sum", 0) or 0)
    out["message"] = data.get("message")

    cert = out["certificate_id"]
    if out["success"] and cert:
        out["hash_ok"] = cert == expected_hash
        if not out["hash_ok"]:
            out["success"] = False
            out["message"] = "хэш сертификата не совпадает с SHA-256 архива"
    elif not out["success"] and not out["message"] and resp.text:
        out["message"] = resp.text[:500]

    return out


def format_certification_markdown(
    info: dict[str, Any],
    prep_error: str,
    *,
    repo_root: Path | None = None,
) -> str:
    """Текст блока для Markdown (подробный отчёт и сводка)."""
    lines: list[str] = []
    lines.append("## Стоимость сертификации и ответ Регулятора\n\n")
    if prep_error:
        pe = prep_error.replace("|", "\\|").replace("`", "'")[:2000]
        lines.append(
            "- **Подготовка пакета:** ошибка или не выполнена — "
            f"`{pe}`\n",
        )
        lines.append("")
        return "".join(lines)

    ok = info.get("success")
    cost = float(info.get("estimated_cost", 0.0) or 0.0)
    loc = int(info.get("tcb_lines_of_code", 0) or 0)
    cc = int(info.get("tcb_cyclomatic_sum", 0) or 0)
    cert = info.get("certificate_id")
    msg = info.get("message")

    stat = "успешно" if ok else "неуспешно"
    lines.append(f"- **Результат сертификации:** {stat}\n")
    lines.append(f"- **Оценочная стоимость (условные ед.):** {cost:.2f}\n")
    lines.append(
        f"- **ДВБ:** строк кода abu={loc}, сумма цикломатики={cc}\n",
    )
    if cert:
        lines.append(f"- **Идентификатор (SHA-256 пакета):** `{cert}`\n")
    elif ok:
        lines.append("- **Идентификатор (SHA-256 пакета):** —\n")

    hash_ok = info.get("hash_ok")
    if hash_ok is not None:
        lines.append(f"- **Совпадение хэша с архивом:** {hash_ok}\n")

    if msg and (not ok or info.get("hash_ok") is False):
        safe = str(msg).replace("|", "\\|").replace("`", "'")[:900]
        lines.append(f"- **Сообщение:** {safe}\n")

    if repo_root is not None:
        mp = (repo_root / "artifacts" / "cert_bundle" / "manifest.json").resolve()
        if mp.is_file():
            try:
                mj = json.loads(mp.read_text(encoding="utf-8"))
                if (
                    "domain_ipc_untrusted_boundary_edges" in mj
                    or "domain_ipc_trusted_boundary_edges" in mj
                ):
                    u = int(mj.get("domain_ipc_untrusted_boundary_edges") or 0)
                    tt = int(mj.get("domain_ipc_trusted_boundary_edges") or 0)
                    lines.append(
                        "- **Междоменные потоки (manifest IPC):** "
                        f"недоверенная граница={u} рёбер, "
                        f"доверенная граница={tt} рёбер (×2 вклад см. regulator/cost_model)\n"
                    )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass

    lines.append("")
    return "".join(lines)


def summary_certification_cell(info: dict[str, Any], prep_error: str) -> str:
    """Одна ячейка для сводной таблицы (markdown-safe)."""
    if prep_error:
        return "ошибка подготовки пакета; см. detailed"
    if not info:
        return "—"
    cost = float(info.get("estimated_cost", 0.0) or 0.0)
    ok = bool(info.get("success"))
    h_ok = info.get("hash_ok")
    if ok and h_ok is not False:
        return f"{cost:.2f} усл. ед."
    tail = ""
    msg = info.get("message")
    if msg:
        tail = str(msg).replace("\n", " ")[:100]
    if cost:
        stub = f"оценочно {cost:.2f} усл. ед."
        if tail:
            return f"{stub}; неуспешно: {tail}"
        return f"{stub}; неуспешно"
    if tail:
        return f"неуспешно: {tail}"
    return "неуспешно"
