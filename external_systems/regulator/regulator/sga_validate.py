"""Проверка документа SGA (security goals and assumptions) в пакете сертификации."""

from __future__ import annotations

import json
import re
from pathlib import Path

REQUIRED_SG_IDS = frozenset(
    {
        "SG_ADS_Authorized_critical_commands",
        "SG_ADS_Controlled_operations",
        "SG_ADS_Security_events_store",
    }
)
REQUIRED_SA_IDS = frozenset({"SA_ADS_Trustrworthy_authorized_operators"})


def load_sga(path: Path) -> tuple[bool, dict | None, str]:
    """
    Загружает и валидирует sga.json.

    :returns: (ok, data или None, сообщение об ошибке)
    """
    if not path.is_file():
        return False, None, "нет security/sga.json в пакете"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, None, f"sga.json: невалидный JSON: {exc}"

    goals = data.get("security_goals") or []
    assump = data.get("security_assumptions") or []
    if not isinstance(goals, list) or not isinstance(assump, list):
        return False, None, "sga.json: security_goals и security_assumptions должны быть списками"
    if not goals or not assump:
        return False, None, "sga.json: пустые security_goals или security_assumptions"

    sg_ids: set[str] = set()
    for g in goals:
        if not isinstance(g, dict):
            return False, None, "sga.json: элемент security_goals должен быть объектом"
        gid = g.get("id")
        st = g.get("statement")
        if not gid or not st:
            return False, None, "sga.json: у каждой ЦБ нужны id и statement"
        if not isinstance(gid, str) or not re.match(r"^SG_[A-Za-z0-9_]+$", gid):
            return False, None, f"sga.json: неверный формат id ЦБ: {gid!r}"
        sg_ids.add(gid)

    sa_ids: set[str] = set()
    for a in assump:
        if not isinstance(a, dict):
            return False, None, "sga.json: элемент security_assumptions должен быть объектом"
        aid = a.get("id")
        st = a.get("statement")
        if not aid or not st:
            return False, None, "sga.json: у каждого ПБ нужны id и statement"
        if not isinstance(aid, str) or not re.match(r"^SA_[A-Za-z0-9_]+$", aid):
            return False, None, f"sga.json: неверный формат id ПБ: {aid!r}"
        sa_ids.add(aid)

    if not REQUIRED_SG_IDS.issubset(sg_ids):
        missing = REQUIRED_SG_IDS - sg_ids
        return False, None, f"sga.json: отсутствуют обязательные ЦБ: {sorted(missing)}"
    if not REQUIRED_SA_IDS.issubset(sa_ids):
        missing = REQUIRED_SA_IDS - sa_ids
        return False, None, f"sga.json: отсутствуют обязательные ПБ: {sorted(missing)}"

    return True, data, "ok"


def sga_document_for_response(data: dict) -> dict:
    """Срез для API."""
    return {
        "security_goals": data.get("security_goals", []),
        "security_assumptions": data.get("security_assumptions", []),
    }
