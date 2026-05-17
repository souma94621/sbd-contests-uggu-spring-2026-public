"""Оценка стоимости сертификации: ДВБ стимулирует малые графы связей, а не «массу» компонентов."""

from __future__ import annotations

import json
import re
from pathlib import Path

# Вклад «прочего» SBOM в итоговую стоимость (понижающий коэффициент).
SBOM_OTHER_COST_DIVISOR = 100

# Крупные зависимости в ДВБ: при наличии в SBOM_TCB или requirements — множитель к стоимости.
HEAVY_DV_B_DEPS = ("numpy",)
HEAVY_DEP_COST_MULTIPLIER = 2.0

# Дополнительный вклад исходного кода ДВБ (пакет abu в сертификационном архиве): строки и цикломатика.
LOC_COST_PER_LINE = 0.15
CC_COST_PER_POINT = 0.8
# В режиме разбиения по доменам: небольшой выпуклый член по каждому dom(LOC).
DOMAIN_LOC_QUADRATIC_COEFF = 8.0e-5
# Стоимость верификации домена растёт с числом правил Белого Списка «входящие разрешённые IPC на d» (from != to).
POLICY_RD_LINEAR = 12.0
POLICY_RD_QUADRATIC = 0.85

# SBOM_TCB: число компонентов N не входит в стоимость — допускается дробление ДВБ на много малых доменов.
# Штрафуются рёбра графа зависимостей E (связи между компонентами/доменами).
TCB_SBOM_BASE = 1000.0
TCB_EDGE_LINEAR = 25.0
TCB_EDGE_QUADRATIC = 1.8

# Междоменные коммуникации (декларируются в manifest сертификационного пакета):
# рёбра на границе **доверенных** доменов безопасности стоят дороже, чем на границе с недоверенной зоной.
DOMAIN_IPC_EDGE_UNIT = TCB_EDGE_LINEAR
DOMAIN_IPC_TRUSTED_VS_UNTRUSTED_FACTOR = 2.0

# SBOM_OTHER (до деления на divisor): без штрафа за число компонентов, только база и рёбра.
OTHER_SBOM_BASE = 500.0
OTHER_EDGE_LINEAR = 0.5


def estimate_tcb_sbom_cost(edges: int) -> float:
    """
    Вклад CycloneDX SBOM_TCB в условных единицах.

    Формула не зависит от числа компонентов (доменов безопасности) — только от числа рёбер E
    (связей между компонентами в графе зависимостей), линейно и квадратично, чтобы стимулировать
    слабосвязанные малые домены безопасности.

    :param edges: число рёбер зависимостей в SBOM_TCB
    """
    e = float(max(0, edges))
    return TCB_SBOM_BASE + TCB_EDGE_LINEAR * e + TCB_EDGE_QUADRATIC * e * e


def estimate_other_sbom_cost(edges: int) -> float:
    """
    Вклад CycloneDX SBOM_OTHER до деления на divisor.

    Число компонентов не входит — только рёбра прочего графа (по смыслу согласовано с TCB).
    """
    e = float(max(0, edges))
    return OTHER_SBOM_BASE + OTHER_EDGE_LINEAR * e


def tcb_partition_verification_addon(
    domain_rows: list[tuple[str, int, int]],
    incoming_ipc_allow_counts: dict[str, int],
) -> tuple[float, list[dict[str, float | int | str]]]:
    """
    Сумма стоимостей верификации по каждому объявленному домену: линейно по LOC/CC,
    квадратично по объёму домена и по числу входящих IPC-разрешений политики (R_d).
    """
    total = 0.0
    rows_out: list[dict[str, float | int | str]] = []
    for did, loc, cc in domain_rows:
        loc_f = float(max(0, loc))
        cc_f = float(max(0, cc))
        base = LOC_COST_PER_LINE * loc_f + CC_COST_PER_POINT * cc_f
        base += DOMAIN_LOC_QUADRATIC_COEFF * (loc_f * loc_f)
        r_d = float(max(0, int(incoming_ipc_allow_counts.get(did, 0))))
        pol = POLICY_RD_LINEAR * r_d + POLICY_RD_QUADRATIC * r_d * r_d
        piece = float(base + pol)
        total += piece
        rows_out.append(
            {
                "domain_id": did,
                "loc": loc,
                "cyclomatic_sum": cc,
                "incoming_ipc_allow_rules": int(r_d),
                "verification_contribution": round(piece, 6),
                "policy_terms": round(float(pol), 6),
            }
        )
    return total, rows_out


def tcb_source_cost_addon(tcb_loc: int, tcb_cyclomatic_sum: int) -> float:
    """
    Дополнительная стоимость по метрикам исходников ДВБ (строки и суммарная цикломатика функций).

    :param tcb_loc: строки *.py, учитываемые как ДВБ (весь ``abu``, если нет парных каталогов
      ``abu/tcb`` и ``abu/other`` в поставке; иначе только ``abu/tcb``, см. ``compute_tcb_source_metrics``)
    :param tcb_cyclomatic_sum: сумма цикломатических сложностей по всем функциям/методам
    """
    return float(LOC_COST_PER_LINE) * float(tcb_loc) + float(CC_COST_PER_POINT) * float(
        tcb_cyclomatic_sum
    )


def estimate_domain_ipc_communication_cost(
    untrusted_boundary_edges: int,
    trusted_boundary_edges: int,
) -> float:
    """
    Условная стоимость потоков данных через границу доменов (входящих/исходящих).

    Рёбра на границе **доверенных** доменов (внутри контура ДВБ) учитываются с коэффициентом
    DOMAIN_IPC_TRUSTED_VS_UNTRUSTED_FACTOR относительно рёбер на границе с недоверенной зоной.
    """
    u = float(max(0, untrusted_boundary_edges))
    t = float(max(0, trusted_boundary_edges))
    return float(DOMAIN_IPC_EDGE_UNIT) * (u + DOMAIN_IPC_TRUSTED_VS_UNTRUSTED_FACTOR * t)


def total_estimated_cost(
    n_tcb: int,
    n_tcb_edges: int,
    n_other: int,
    n_other_edges: int,
    *,
    tcb_loc: int = 0,
    tcb_cyclomatic_sum: int = 0,
    ipc_untrusted_boundary_edges: int = 0,
    ipc_trusted_boundary_edges: int = 0,
    tcb_domain_partition: list[tuple[str, int, int]] | None = None,
    policy_incoming_allow_counts_by_domain: dict[str, int] | None = None,
    tcb_source_verification_addon: float | None = None,
) -> float:
    """
    Итоговая стоимость: SBOM_TCB (только по рёбрам E), исходники ДВБ (см. **tcb_loc** в коде —
    весь ``abu``, если структурного разведения доменов в дереве ``abu/tcb`` + ``abu/other`` нет),
    SBOM_OTHER / divisor,
    плюс учёт междоменных потоков (**ipc_***) по manifest.

    Параметры n_tcb и n_other сохраняются в сигнатуре для совместимости с парсером SBOM и
    отладки; в формулу стоимости не входят.

    Если задан ``tcb_source_verification_addon``, он используется вместо расчёта по
    ``tcb_loc``/разбиению (последний случай для unit-тестов с предвычисленной суммой).
    """
    _ = n_tcb, n_other  # метрики компонентов не штрафуются
    if tcb_source_verification_addon is not None:
        tcb_code_addon = float(tcb_source_verification_addon)
    elif tcb_domain_partition:
        ipc_counts = policy_incoming_allow_counts_by_domain or {}
        tcb_code_addon, _ = tcb_partition_verification_addon(tcb_domain_partition, ipc_counts)
    else:
        tcb_code_addon = tcb_source_cost_addon(tcb_loc, tcb_cyclomatic_sum)
    cost_tcb = estimate_tcb_sbom_cost(n_tcb_edges) + tcb_code_addon
    cost_other = estimate_other_sbom_cost(n_other_edges)
    ipc = estimate_domain_ipc_communication_cost(
        ipc_untrusted_boundary_edges,
        ipc_trusted_boundary_edges,
    )
    return cost_tcb + cost_other / float(SBOM_OTHER_COST_DIVISOR) + ipc


def sbom_has_heavy_dep(sbom_path: Path, heavy_names: tuple[str, ...] = HEAVY_DV_B_DEPS) -> bool:
    """Проверяет, есть ли в CycloneDX компонент с именем из heavy_names (без учёта регистра)."""
    if not sbom_path.is_file():
        return False
    data = json.loads(sbom_path.read_text(encoding="utf-8"))
    components = data.get("components") or []
    lowered = {n.lower() for n in heavy_names}
    for comp in components:
        name = (comp.get("name") or "").lower()
        if name in lowered:
            return True
    return False


def requirements_has_heavy_dep(req_path: Path, heavy_names: tuple[str, ...] = HEAVY_DV_B_DEPS) -> bool:
    """Проверяет requirements.txt на упоминание пакета (строка начинается с имени)."""
    if not req_path.is_file():
        return False
    text = req_path.read_text(encoding="utf-8", errors="replace")
    lowered = {n.lower() for n in heavy_names}
    for line in text.splitlines():
        line = line.strip().split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        pkg = re.split(r"[<>=!~\[\s;]", line, maxsplit=1)[0].strip().lower()
        if pkg in lowered:
            return True
    return False


def apply_heavy_dep_multiplier(
    base_cost: float,
    sbom_tcb_path: Path | None,
    requirements_path: Path | None,
) -> float:
    """Удваивает стоимость, если numpy и т.п. присутствуют в ДВБ (SBOM_TCB или requirements)."""
    if sbom_tcb_path and sbom_has_heavy_dep(sbom_tcb_path):
        return base_cost * HEAVY_DEP_COST_MULTIPLIER
    if requirements_path and requirements_has_heavy_dep(requirements_path):
        return base_cost * HEAVY_DEP_COST_MULTIPLIER
    return base_cost
