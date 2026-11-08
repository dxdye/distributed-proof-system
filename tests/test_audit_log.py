from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dpc.audit import GENESIS_HASH, AuditLog

pytestmark = pytest.mark.req("SR-19")


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def log(tmp_path: Path) -> AuditLog:
    return AuditLog(tmp_path / "audit.sqlite", clock=FakeClock())


def _raw(path: Path) -> sqlite3.Connection:
    """Direct database access, as an attacker with file access would have."""
    return sqlite3.connect(path, isolation_level=None)


def test_entries_are_chained(log: AuditLog) -> None:
    first = log.append("submission.received", {"repo": "x"})
    second = log.append("build.completed", {"ok": True})
    assert (first.seq, second.seq) == (0, 1)
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash
    assert log.verify().ok
    assert log.verify().length == 2


def test_same_events_give_same_hashes(tmp_path: Path) -> None:
    heads = []
    for name in ("a", "b"):
        with AuditLog(tmp_path / f"{name}.sqlite", clock=FakeClock()) as log:
            log.append("x.created", {"n": 1})
            heads.append(log.append("x.changed", {"n": 2}).hash)
    assert heads[0] == heads[1]


def test_rejects_invalid_kind_and_floats(log: AuditLog) -> None:
    with pytest.raises(ValueError):
        log.append("NoDots", {})
    with pytest.raises(ValueError):
        log.append("trust.updated", {"kappa": 0.5})
    assert len(log) == 0


def test_update_and_delete_are_blocked(tmp_path: Path) -> None:
    path = tmp_path / "audit.sqlite"
    with AuditLog(path) as log:
        log.append("x.created", {"n": 1})
    conn = _raw(path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE audit_log SET payload = '{\"n\":2}'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM audit_log")


def test_tampering_is_detected_even_without_triggers(tmp_path: Path) -> None:
    path = tmp_path / "audit.sqlite"
    with AuditLog(path, clock=FakeClock()) as log:
        for n in range(5):
            log.append("x.changed", {"n": n})
    conn = _raw(path)
    conn.execute("DROP TRIGGER audit_log_no_update")
    conn.execute("UPDATE audit_log SET payload = '{\"n\":99}' WHERE seq = 2")
    with AuditLog(path) as log:
        result = log.verify()
    assert not result.ok
    assert result.first_bad_seq == 2
    assert "hash mismatch" in (result.reason or "")


def test_removing_an_entry_breaks_the_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.sqlite"
    with AuditLog(path, clock=FakeClock()) as log:
        for n in range(4):
            log.append("x.changed", {"n": n})
    conn = _raw(path)
    conn.execute("DROP TRIGGER audit_log_no_delete")
    conn.execute("DELETE FROM audit_log WHERE seq = 1")
    with AuditLog(path) as log:
        result = log.verify()
    assert not result.ok
    assert result.first_bad_seq == 1


def test_truncation_needs_published_head(tmp_path: Path) -> None:
    path = tmp_path / "audit.sqlite"
    with AuditLog(path, clock=FakeClock()) as log:
        log.append("x.changed", {"n": 0})
        published = log.append("report.published", {"n": 1}).hash
    conn = _raw(path)
    conn.execute("DROP TRIGGER audit_log_no_delete")
    conn.execute("DELETE FROM audit_log WHERE seq = 1")
    with AuditLog(path) as log:
        assert log.verify().ok  # the remaining prefix is a valid chain …
        assert not log.verify(expected_head=published).ok  # … but not the published one


def test_concurrent_writers_keep_a_total_order(tmp_path: Path) -> None:
    path = tmp_path / "audit.sqlite"
    AuditLog(path).close()

    def writer(worker: int) -> None:
        with AuditLog(path) as log:
            for n in range(25):
                log.append("load.test", {"worker": worker, "n": n})

    threads = [threading.Thread(target=writer, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with AuditLog(path) as log:
        result = log.verify()
        assert result.ok
        assert result.length == 100
        assert [e.seq for e in log.entries()] == list(range(100))
