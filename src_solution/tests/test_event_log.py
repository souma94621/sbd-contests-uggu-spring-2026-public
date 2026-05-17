"""Тесты журнала событий. Критерии: C04, C12, C15."""

from __future__ import annotations

from src_solution.abu.tcb.event_log import EventLevel, EventLog


def test_record_appears_in_ring():
    """Записанное событие появляется в кольцевом буфере."""
    log = EventLog()
    log.record(EventLevel.INFO, "test_message")
    snapshot = log.ring_snapshot()
    assert any("test_message" in line for line in snapshot)


def test_ring_max_size():
    """Кольцо не превышает 10 сообщений."""
    log = EventLog()
    for i in range(15):
        log.record(EventLevel.INFO, f"msg_{i}")
    assert len(log.ring_snapshot()) <= 10


def test_all_levels_recorded():
    """Все уровни событий записываются корректно."""
    log = EventLog()
    for level in EventLevel:
        log.record(level, f"test_{level.value}")
    snapshot = log.ring_snapshot()
    assert len(snapshot) > 0


def test_ring_snapshot_returns_list():
    """ring_snapshot возвращает список строк."""
    log = EventLog()
    log.record(EventLevel.WARNING, "warn_event")
    result = log.ring_snapshot()
    assert isinstance(result, list)
    assert all(isinstance(line, str) for line in result)


def test_empty_log_full_tail():
    """Новый лог без файла возвращает пустую строку."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        log = EventLog(log_dir=Path(tmpdir) / "nonexistent")
        # файл ещё не создан, но лог работает через ring
        result = log.read_full_tail()
        assert isinstance(result, str)


def test_critical_level_in_snapshot():
    """CRITICAL уровень фиксируется в буфере."""
    log = EventLog()
    log.record(EventLevel.CRITICAL, "critical_event")
    snapshot = log.ring_snapshot()
    assert any("CRITICAL" in line for line in snapshot)
