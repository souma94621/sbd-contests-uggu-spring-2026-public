"""Проверка SGA АБУ на соответствие политике ЦР (дубли идентификаторов с Регулятором)."""

from __future__ import annotations

REQUIRED_SG_IDS = frozenset(
    {
        "SG_ADS_Authorized_critical_commands",
        "SG_ADS_Controlled_operations",
        "SG_ADS_Security_events_store",
    }
)
REQUIRED_SA_IDS = frozenset({"SA_ADS_Trustrworthy_authorized_operators"})


def validate_sga_payload(data: dict) -> bool:
    """True если в ответе Регулятора есть все обязательные SG/SA."""
    goals = data.get("security_goals") or []
    assump = data.get("security_assumptions") or []
    sg = {g.get("id") for g in goals if isinstance(g, dict)}
    sa = {a.get("id") for a in assump if isinstance(a, dict)}
    return REQUIRED_SG_IDS.issubset(sg) and REQUIRED_SA_IDS.issubset(sa)
