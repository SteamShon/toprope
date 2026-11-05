"""SQLite event store (tests and single-process deployments)."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from typing import Any

from ..types import Event, Outcome
from . import ConcurrencyError, EventStore
from .codec import (
    event_from_json,
    event_to_json,
    key_to_text,
    outcome_from_json,
    outcome_to_json,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  stream TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL,
  UNIQUE (stream, version));
CREATE TABLE IF NOT EXISTS attempts (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, stream TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency (
  key TEXT PRIMARY KEY, outcome TEXT);   -- NULL outcome = claimed, pending
"""


class SQLiteEventStore(EventStore):
    """Each instance owns one connection, and every operation holds the instance lock, so
    threads sharing an instance are serialized and never write inside another thread's
    transaction. For parallelism, open several instances on one file; they really race."""

    def __init__(self, path: str):
        self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=30)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._lock = threading.RLock()

    def close(self) -> None:
        self._db.close()

    def version(self, stream: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT COALESCE(MAX(version), 0) FROM events WHERE stream=?", (stream,)).fetchone()
            return row[0]

    def append(self, stream: str, expected_version: int, events: list[Event]) -> list[Event]:
        out = [replace(e, version=expected_version + i + 1) for i, e in enumerate(events)]
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                if self.version(stream) != expected_version:
                    raise ConcurrencyError(f"{stream}: expected v{expected_version}, at v{self.version(stream)}")
                self._db.executemany("INSERT INTO events (stream, version, body) VALUES (?, ?, ?)",
                                     [(stream, e.version, event_to_json(e)) for e in out])
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._db.execute("ROLLBACK")
                raise ConcurrencyError(str(exc)) from exc
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        # What a read returns, so every adapter normalizes identically (replay parity, ADR-0012).
        return [event_from_json(event_to_json(e)) for e in out]

    def read(self, stream: str) -> list[Event]:
        with self._lock:
            rows = self._db.execute("SELECT body FROM events WHERE stream=? ORDER BY version", (stream,))
            return [event_from_json(r[0]) for r in rows]

    def append_attempt(self, event: Event) -> None:
        with self._lock:
            self._db.execute("INSERT INTO attempts (stream, body) VALUES (?, ?)", (event.stream, event_to_json(event)))

    def read_attempts(self, stream: str) -> list[Event]:
        with self._lock:
            rows = self._db.execute("SELECT body FROM attempts WHERE stream=? ORDER BY seq", (stream,))
            return [event_from_json(r[0]) for r in rows]

    def streams(self) -> list[str]:
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT stream FROM events GROUP BY stream ORDER BY MIN(seq)")]

    def claim(self, key: tuple[Any, ...]):
        with self._lock:
            k = key_to_text(key)
            cur = self._db.execute("INSERT OR IGNORE INTO idempotency (key, outcome) VALUES (?, NULL)", (k,))
            if cur.rowcount == 1:
                return None
            row = self._db.execute("SELECT outcome FROM idempotency WHERE key=?", (k,)).fetchone()
            if row is None:          # released between our insert attempt and the read: try once more
                return self.claim(key)
            return "pending" if row[0] is None else outcome_from_json(row[0])

    def remember(self, key: tuple[Any, ...], outcome: Outcome) -> None:
        with self._lock:
            self._db.execute("UPDATE idempotency SET outcome=? WHERE key=?", (outcome_to_json(outcome), key_to_text(key)))

    def release(self, key: tuple[Any, ...]) -> None:
        with self._lock:
            self._db.execute("DELETE FROM idempotency WHERE key=? AND outcome IS NULL", (key_to_text(key),))
