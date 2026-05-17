"""SG_ADS_Security_events_store — журнал и API событий."""

from __future__ import annotations

import pytest

from abu.event_log import EventLevel, EventLog
from abu.numpy_workflow import smooth_vibration_window


@pytest.mark.security
def test_event_log_ring_and_full(tmp_path) -> None:
    """События попадают в кольцо и полный журнал."""
    log = EventLog(tmp_path)
    for i in range(15):
        log.record(EventLevel.INFO, f"evt-{i}")
    ring = log.ring_snapshot()
    assert len(ring) <= 10
    full = log.read_full_tail()
    assert "evt-14" in full


@pytest.mark.security
def test_numpy_smooth_used_in_stack() -> None:
    """numpy в контуре ДВБ (базовая поставка)."""
    v = smooth_vibration_window([1.0, 2.0, 3.0, 4.0, 5.0])
    assert 2.0 <= v <= 4.0
