"""IPC-тесты для примера secure_ipc."""

import pytest

from references.secure_ipc.domain_guard import DomainGuard
from references.secure_ipc.ipc import Event
from references.secure_ipc.domain_process import DomainProcess
from references.secure_ipc.message_broker import MessageBroker
from references.secure_ipc.operator_ui.domain import DOMAIN_ID as UI
from references.secure_ipc.operator_ui.domain import render_notice
from references.secure_ipc.parameter_guard import ParameterGuard
from references.secure_ipc.route_monitor import RouteMonitor
from references.secure_ipc.tcb_audit.domain import DOMAIN_ID as AUDIT
from references.secure_ipc.tcb_audit.domain import append_event, last_event
from references.secure_ipc.tcb_guard.domain import DOMAIN_ID as GUARD
from references.secure_ipc.tcb_guard.domain import approve


def _broker_with_domains(
    route_monitor: RouteMonitor | None = None,
    domain_guard: DomainGuard | None = None,
    parameter_guard: ParameterGuard | None = None,
):
    """Создать брокер с тремя зарегистрированными доменами примера."""
    broker = MessageBroker(route_monitor, domain_guard, parameter_guard)
    domains = [
        DomainProcess(GUARD, {"approve": approve}),
        DomainProcess(
            AUDIT,
            {"append_event": append_event, "last_event": last_event},
        ),
        DomainProcess(UI, {"render_notice": render_notice}),
    ]
    for domain in domains:
        broker.register(domain)
    return broker, domains


def test_allowed_ipc_route() -> None:
    """Разрешённый маршрут 1 -> 2 достигает домена аудита."""
    broker, domains = _broker_with_domains()
    try:
        result = broker.send(
            Event(GUARD, AUDIT, "append_event", {"message": "ok"}),
        )
        assert result == "ok"
    finally:
        for domain in domains:
            domain.stop()


def test_blocked_direct_route_1_to_3() -> None:
    """Неописанный прямой маршрут 1 -> 3 блокируется запретом по умолчанию."""
    broker, domains = _broker_with_domains()
    try:
        with pytest.raises(PermissionError):
            broker.send(
                Event(GUARD, UI, "render_notice", {"message": "blocked"}),
            )
    finally:
        for domain in domains:
            domain.stop()


def test_route_allowed_but_egress_blocks_operator_ui() -> None:
    """Разрешения маршрута недостаточно, если выход отправителя запрещает."""
    broker, domains = _broker_with_domains()
    try:
        with pytest.raises(PermissionError, match="доменной политикой"):
            broker.send(
                Event(UI, AUDIT, "append_event", {"message": "ui log"}),
            )
    finally:
        for domain in domains:
            domain.stop()


def test_route_allowed_but_ingress_blocks_tcb_guard() -> None:
    """Разрешения маршрута недостаточно, если вход получателя запрещает."""
    broker, domains = _broker_with_domains()
    try:
        with pytest.raises(PermissionError, match="доменной политикой"):
            broker.send(Event(AUDIT, GUARD, "last_event", {}))
    finally:
        for domain in domains:
            domain.stop()


def test_parameter_policy_blocks_bad_payload() -> None:
    """Разрешённая пара доменов всё равно проходит проверку нагрузки."""
    broker, domains = _broker_with_domains()
    try:
        with pytest.raises(PermissionError, match="политикой параметров"):
            broker.send(
                Event(
                    GUARD,
                    AUDIT,
                    "append_event",
                    {"message": "x" * 80},
                ),
            )
    finally:
        for domain in domains:
            domain.stop()


def test_one_weakened_layer_is_not_enough_to_bypass_others() -> None:
    """Ослабление одного слоя не обходит локальную политику домена."""
    permissive_routes = RouteMonitor(frozenset({
        (GUARD, UI, "render_notice"),
    }))
    broker, domains = _broker_with_domains(route_monitor=permissive_routes)
    try:
        with pytest.raises(PermissionError, match="доменной политикой"):
            broker.send(Event(GUARD, UI, "render_notice", {"message": "x"}))
    finally:
        for domain in domains:
            domain.stop()
