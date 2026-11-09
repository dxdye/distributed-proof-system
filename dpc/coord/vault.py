"""Server-side secrets of the coordination service (docs/adr/0008).

Kept apart from the audit log and never published:

* accounts: pseudonym ↔ reviewer id, API tokens (stored as SHA-256 only),
* the key for affiliation tags (keyed hashes in the log, SR-23, SR-50),
* honeypot openings until they are revealed (SR-06, SR-37). The log holds
  only a commitment ``SHA-256(canonical opening)``; revealing the opening later
  proves that the honeypot status was fixed when the ticket was created.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path

from dpc.audit.canonical import canonical_json, sha256_hex
from dpc.coord.events import Opening

_SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts (
    rid TEXT PRIMARY KEY, pseudonym TEXT NOT NULL UNIQUE, token_sha256 TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS openings (
    ticket_id TEXT PRIMARY KEY, submission_id TEXT NOT NULL, opening TEXT NOT NULL,
    honeypot INTEGER NOT NULL, revealed INTEGER NOT NULL DEFAULT 0
);
"""


def commitment(opening: Opening) -> str:
    return sha256_hex(canonical_json(opening.model_dump()))


def normalise_label(text: str) -> str:
    return " ".join(text.casefold().split())


class Vault:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        row = self._conn.execute("SELECT value FROM keys WHERE name = 'tag'").fetchone()
        if row is None:
            key = secrets.token_hex(32)
            self._conn.execute("INSERT INTO keys VALUES ('tag', ?)", (key,))
        else:
            key = row[0]
        self._tag_key = bytes.fromhex(key)

    def close(self) -> None:
        self._conn.close()

    # --------------------------------------------------------------- tags
    def tag(self, label: str) -> str:
        """Keyed hash of an affiliation or lab name (SR-23, SR-50)."""
        msg = normalise_label(label).encode("utf-8")
        return hmac.new(self._tag_key, msg, hashlib.sha256).hexdigest()

    # ----------------------------------------------------------- accounts
    def create_account(self, pseudonym: str) -> tuple[str, str]:
        """New reviewer id and API token (returned once, stored hashed)."""
        rid = f"R-{secrets.token_hex(6)}"
        token = secrets.token_urlsafe(32)
        try:
            self._conn.execute("INSERT INTO accounts VALUES (?, ?, ?)",
                               (rid, pseudonym, sha256_hex(token.encode())))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"pseudonym {pseudonym!r} is taken") from exc
        return rid, token

    def reviewer_for_token(self, token: str) -> str | None:
        row = self._conn.execute("SELECT rid FROM accounts WHERE token_sha256 = ?",
                                 (sha256_hex(token.encode()),)).fetchone()
        return None if row is None else str(row[0])

    def reviewer_for_pseudonym(self, pseudonym: str) -> str | None:
        row = self._conn.execute("SELECT rid FROM accounts WHERE pseudonym = ?",
                                 (pseudonym,)).fetchone()
        return None if row is None else str(row[0])

    def pseudonym(self, rid: str) -> str | None:
        row = self._conn.execute("SELECT pseudonym FROM accounts WHERE rid = ?",
                                 (rid,)).fetchone()
        return None if row is None else str(row[0])

    # ----------------------------------------------------------- openings
    def put_opening(self, submission_id: str, opening: Opening) -> str:
        self._conn.execute(
            "INSERT INTO openings(ticket_id, submission_id, opening, honeypot) VALUES (?,?,?,?)",
            (opening.ticket_id, submission_id, opening.model_dump_json(), int(opening.honeypot)))
        return commitment(opening)

    def unrevealed(self, *, honeypots_only: bool, submission_id: str | None = None
                   ) -> list[Opening]:
        query = "SELECT opening FROM openings WHERE revealed = 0"
        args: list[str] = []
        if honeypots_only:
            query += " AND honeypot = 1"
        if submission_id is not None:
            query += " AND submission_id = ?"
            args.append(submission_id)
        rows = self._conn.execute(query + " ORDER BY ticket_id", args).fetchall()
        return [Opening.model_validate_json(r[0]) for r in rows]

    def mark_revealed(self, ticket_ids: list[str]) -> None:
        self._conn.executemany("UPDATE openings SET revealed = 1 WHERE ticket_id = ?",
                               [(t,) for t in ticket_ids])

    def is_honeypot(self, ticket_id: str) -> bool:
        """Server-side only; never exposed through the reviewer API."""
        row = self._conn.execute("SELECT honeypot FROM openings WHERE ticket_id = ?",
                                 (ticket_id,)).fetchone()
        return bool(row and row[0])


class BlobStore:
    """Content-addressed files (Lean evidence, SR-09)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> str:
        digest = sha256_hex(data)
        path = self.root / digest
        if not path.exists():
            path.write_bytes(data)
        return digest

    def get(self, digest: str) -> bytes:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("not a SHA-256 digest")
        return (self.root / digest).read_bytes()
