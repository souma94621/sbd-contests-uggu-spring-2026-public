"""Модульные тесты журнала событий."""

from __future__ import annotations

from abu.event_log import EventLevel, EventLog


def test_ring_maxlen(tmp_path) -> None:
    """Кольцо не больше 10 записей."""
    log = EventLog(tmp_path)
    for i in range(12):
        log.record(EventLevel.INFO, str(i))
    assert len(log.ring_snapshot()) == 10


def test_record_and_snapshot(tmp_path) -> None:
    """Запись и снимок кольца."""
    log = EventLog(tmp_path)
    log.record(EventLevel.WARNING, "test")
    snap = log.ring_snapshot()
    assert len(snap) == 1
    assert "WARNING" in snap[0]


def test_full_tail(tmp_path) -> None:
    """Хвост полного журнала."""
    log = EventLog(tmp_path)
    log.record(EventLevel.ERROR, "error1")
    log.record(EventLevel.CRITICAL, "error2")
    tail = log.read_full_tail()
    assert "error1" in tail
    assert "error2" in tail


def test_multiple_records(tmp_path) -> None:
    """Несколько записей."""
    log = EventLog(tmp_path)
    log.record(EventLevel.INFO, "info")
    log.record(EventLevel.WARNING, "warn")
    snap = log.ring_snapshot()
    assert len(snap) == 2
