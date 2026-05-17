"""Загрузка декларативного ipc_policies.json и метрики R_d для стоимости."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_ipc_policies(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return raw


def count_incoming_cross_domain_ipc_allows(policy: dict[str, Any]) -> dict[str, int]:
    """
    Для домена ``d``: число записей вида разрешённые «чужие → d» (from != to),
    см. задачу: стоимость верификации дешевле узких входящих разрешений.
    """
    out: dict[str, int] = {}
    rules = policy.get("allows") or []
    if not isinstance(rules, list):
        return out
    for ent in rules:
        if not isinstance(ent, dict):
            continue
        fr = ent.get("from")
        to = ent.get("to")
        if fr is None or to is None:
            continue
        if fr == to:
            continue
        key = str(to)
        out[key] = out.get(key, 0) + 1
    return out
