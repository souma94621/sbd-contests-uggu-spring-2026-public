"""Тесты изолированных доменов, общающихся только через очереди."""

import pytest

from references.isolation.ipc import DomainProcess, Event
from references.isolation.sensor_adapter.domain import DOMAIN_ID as SENSOR
from references.isolation.sensor_adapter.domain import read_depth
from references.isolation.tcb_controller.domain import (
    DOMAIN_ID as TCB_CONTROLLER,
)
from references.isolation.tcb_controller.domain import approve_depth


def test_send_does_not_wait_for_response() -> None:
    """Отправка события возвращает request_id без чтения результата."""
    sensor = DomainProcess(SENSOR, {"read_depth": read_depth})
    try:
        request_id = sensor.send(
            Event(TCB_CONTROLLER, SENSOR, "read_depth", {"depth_m": 42}),
        )
        assert isinstance(request_id, str)
        assert request_id
    finally:
        sensor.stop()


def test_domain_processes_incoming_request_asynchronously() -> None:
    """Домены обрабатывают inbox-события и отдельно публикуют результат."""
    sensor = DomainProcess(SENSOR, {"read_depth": read_depth})
    controller = DomainProcess(
        TCB_CONTROLLER,
        {"approve_depth": approve_depth},
    )
    try:
        depth_request = sensor.send(
            Event(TCB_CONTROLLER, SENSOR, "read_depth", {"depth_m": 42}),
        )
        depth = sensor.receive(depth_request)
        assert depth == 42.0
        approval_request = controller.send(
            Event(
                SENSOR,
                TCB_CONTROLLER,
                "approve_depth",
                {"depth_m": depth, "max_depth_m": 50},
            ),
        )
        allowed = controller.receive(approval_request)
        assert allowed is True
    finally:
        sensor.stop()
        controller.stop()


def test_unknown_operation_reports_error_asynchronously() -> None:
    """Неизвестная операция отправляется, но ошибка видна при receive."""
    controller = DomainProcess(
        TCB_CONTROLLER,
        {"approve_depth": approve_depth},
    )
    try:
        request_id = controller.send(
            Event(SENSOR, TCB_CONTROLLER, "delete_everything", {}),
        )
        with pytest.raises(RuntimeError, match="неизвестная операция"):
            controller.receive(request_id)
    finally:
        controller.stop()
