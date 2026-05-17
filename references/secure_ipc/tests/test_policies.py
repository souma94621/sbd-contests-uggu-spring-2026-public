"""Тесты политик для примера secure_ipc."""

from references.secure_ipc.ipc import Event
from references.secure_ipc.route_monitor import RouteMonitor, load_allows


def test_policy_allows_chain_and_blocks_direct_1_to_3() -> None:
    """Whitelist разрешает цепочку 1 <-> 2 и 2 <-> 3, но блокирует 1 -> 3."""
    monitor = RouteMonitor(load_allows())
    assert monitor.check(Event("tcb_guard", "tcb_audit", "append_event", {}))
    assert monitor.check(
        Event("tcb_audit", "operator_ui", "render_notice", {}),
    )
    assert monitor.check(Event("operator_ui", "tcb_audit", "append_event", {}))
    assert not monitor.check(
        Event("tcb_guard", "operator_ui", "render_notice", {}),
    )


def test_policy_blocks_malformed_event() -> None:
    """Маршрутная политика отклоняет объекты, не являющиеся Event."""
    monitor = RouteMonitor(load_allows())
    assert monitor.check({"source": "tcb_guard"}) is False
