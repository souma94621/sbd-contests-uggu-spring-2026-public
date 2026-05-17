"""Учёт междоменных рёбер стоимости (manifest + cost_model)."""

from __future__ import annotations

import pytest

from regulator.cost_model import (
    DOMAIN_IPC_EDGE_UNIT,
    DOMAIN_IPC_TRUSTED_VS_UNTRUSTED_FACTOR,
    estimate_domain_ipc_communication_cost,
    total_estimated_cost,
)


def test_ipc_trusted_edge_costs_twice_untrusted_margin() -> None:
    """На единицу рёбер: доверенный край дороже в DOMAIN_IPC_TRUSTED_VS_UNTRUSTED_FACTOR раз."""
    ut = estimate_domain_ipc_communication_cost(4, 0)
    tr = estimate_domain_ipc_communication_cost(0, 2)
    assert ut == 4.0 * DOMAIN_IPC_EDGE_UNIT
    assert tr == 2.0 * DOMAIN_IPC_EDGE_UNIT * DOMAIN_IPC_TRUSTED_VS_UNTRUSTED_FACTOR
    assert estimate_domain_ipc_communication_cost(2, 1) == pytest.approx(
        DOMAIN_IPC_EDGE_UNIT * (2.0 + DOMAIN_IPC_TRUSTED_VS_UNTRUSTED_FACTOR),
    )


def test_ipc_two_untrusted_plus_one_trusted_equals_four_untrusted() -> None:
    assert estimate_domain_ipc_communication_cost(2, 1) == estimate_domain_ipc_communication_cost(
        4, 0
    )


def test_total_estimated_cost_ipc_defaults_zero() -> None:
    a = total_estimated_cost(1, 1, 2, 3, tcb_loc=10, tcb_cyclomatic_sum=5)
    b = total_estimated_cost(
        1,
        1,
        2,
        3,
        tcb_loc=10,
        tcb_cyclomatic_sum=5,
        ipc_untrusted_boundary_edges=0,
        ipc_trusted_boundary_edges=0,
    )
    assert a == b
