"""Append-only, hash-chained audit log (component C11, SR-19).

Every state change of the system is an event in this log; all other state is a
projection of it (docs/adr/0002). Entry ``n`` stores the SHA-256 of entry
``n-1``, so altering, reordering or removing an entry breaks the chain from that
point on. Truncating the *tail* is only detectable against a published head
hash, which is why reports carry the head hash (interface I-5) and
:meth:`AuditLog.verify` accepts an ``expected_head``.

Single writer: appends run in an ``IMMEDIATE`` transaction, which serialises
concurrent writers; the chain is a total order and never needs consensus
(docs/adr/0003).
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dpc.audit.canonical import canonical_json, sha256_hex

GENESIS_HASH = "0" * 64

_KIND = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    seq       INTEGER PRIMARY KEY,   -- 0, 1, 2, ... without gaps
    ts        TEXT NOT NULL,         -- ISO-8601 UTC, second precision
    kind      TEXT NOT NULL,         -- dotted event type, e.g. "analysis.completed"
    payload   TEXT NOT NULL,         -- canonical JSON
    prev_hash TEXT NOT NULL,
    hash      TEXT NOT NULL UNIQUE
);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_ts(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def entry_hash(seq: int, ts: str, kind: str, payload: Mapping[str, Any], prev_hash: str) -> str:
    body = {"seq": seq, "ts": ts, "kind": kind, "payload": payload, "prev": prev_hash}
    return sha256_hex(canonical_json(body))


@dataclass(frozen=True)
class Entry:
    seq: int
    ts: str
    kind: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


@dataclass(frozen=True)
class Verification:
    ok: bool
    length: int
    head_hash: str
    first_bad_seq: int | None = None
    reason: str | None = None


class AuditLog:
    """SQLite-backed audit log. Use as a context manager or call :meth:`close`."""

    def __init__(self, path: str | Path, clock: Callable[[], datetime] = utc_now) -> None:
        self._path = str(path)
        self._clock = clock
        # Autocommit mode; transactions are opened explicitly in `append`.
        self._conn = sqlite3.connect(self._path, isolation_level=None, timeout=30.0)
        self._conn.executescript(_SCHEMA)

    def __enter__(self) -> AuditLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ write
    def append(self, kind: str, payload: Mapping[str, Any]) -> Entry:
        """Append one event and return the stored entry."""
        if not _KIND.match(kind):
            raise ValueError(f"invalid event kind {kind!r} (expected e.g. 'analysis.completed')")
        payload_text = canonical_json(payload).decode("utf-8")
        ts = format_ts(self._clock())
        cur = self._conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            row = cur.execute(
                "SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            seq, prev = (0, GENESIS_HASH) if row is None else (row[0] + 1, row[1])
            data = json.loads(payload_text)
            digest = entry_hash(seq, ts, kind, data, prev)
            cur.execute(
                "INSERT INTO audit_log(seq, ts, kind, payload, prev_hash, hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (seq, ts, kind, payload_text, prev, digest),
            )
            cur.execute("COMMIT")
        except BaseException:
            cur.execute("ROLLBACK")
            raise
        return Entry(seq, ts, kind, data, prev, digest)

    # ------------------------------------------------------------------- read
    def head(self) -> Entry | None:
        row = self._conn.execute(
            "SELECT seq, ts, kind, payload, prev_hash, hash FROM audit_log "
            "ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return None if row is None else self._entry(row)

    def entries(self, start: int = 0) -> Iterator[Entry]:
        rows = self._conn.execute(
            "SELECT seq, ts, kind, payload, prev_hash, hash FROM audit_log "
            "WHERE seq >= ? ORDER BY seq",
            (start,),
        )
        for row in rows:
            yield self._entry(row)

    def __len__(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])

    @staticmethod
    def _entry(row: tuple[Any, ...]) -> Entry:
        seq, ts, kind, payload, prev, digest = row
        return Entry(int(seq), str(ts), str(kind), json.loads(payload), str(prev), str(digest))

    # ----------------------------------------------------------------- verify
    def verify(self, expected_head: str | None = None) -> Verification:
        """Recompute the whole chain. ``expected_head`` detects truncation."""
        prev = GENESIS_HASH
        length = 0
        rows = self._conn.execute(
            "SELECT seq, ts, kind, payload, prev_hash, hash FROM audit_log ORDER BY seq"
        )
        for seq, ts, kind, payload_text, prev_hash, digest in rows:
            problem = self._check_entry(
                length, prev, int(seq), str(ts), str(kind), str(payload_text), str(prev_hash),
                str(digest),
            )
            if problem is not None:
                return Verification(False, length, prev, min(int(seq), length), problem)
            prev = str(digest)
            length += 1
        if expected_head is not None and expected_head != prev:
            return Verification(False, length, prev, length, "head differs from expected head")
        return Verification(True, length, prev)

    @staticmethod
    def _check_entry(
        expected_seq: int, prev: str, seq: int, ts: str, kind: str, payload_text: str,
        prev_hash: str, digest: str,
    ) -> str | None:
        """Reason why this entry breaks the chain, or ``None``."""
        if seq != expected_seq:
            return f"gap in sequence: expected {expected_seq}, found {seq}"
        if prev_hash != prev:
            return "prev_hash does not match the previous entry"
        try:
            payload = json.loads(payload_text)
            canonical = canonical_json(payload).decode("utf-8")
        except ValueError as exc:
            return f"payload is not canonical JSON: {exc}"
        if canonical != payload_text:
            return "payload is not in canonical form"
        if entry_hash(seq, ts, kind, payload, prev) != digest:
            return "hash mismatch (entry was altered)"
        return None
