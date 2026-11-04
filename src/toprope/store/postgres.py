"""PostgreSQL event store in its own schema (ADR-0012). Requires the `postgres` extra (psycopg 3)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import psycopg
from psycopg import sql

from ..types import Event, Outcome
from . import ConcurrencyError, EventStore
from .codec import event_from_json, event_to_json, key_to_text, outcome_from_json, outcome_to_json


def _ddl(schema: str) -> sql.Composed:
    s = sql.Identifier(schema)
    return sql.SQL("""
CREATE SCHEMA IF NOT EXISTS {s};
CREATE TABLE IF NOT EXISTS {s}.events (
  seq BIGSERIAL PRIMARY KEY, stream TEXT NOT NULL, version INTEGER NOT NULL, body JSONB NOT NULL,
  UNIQUE (stream, version));
CREATE TABLE IF NOT EXISTS {s}.attempts (
  seq BIGSERIAL PRIMARY KEY, stream TEXT NOT NULL, body JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS {s}.idempotency (key TEXT PRIMARY KEY, outcome JSONB);
""").format(s=s)


class PostgresEventStore(EventStore):
    """One connection per instance (autocommit; explicit transactions where needed)."""

    def __init__(self, dsn: str, schema: str = "toprope"):
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._s = sql.Identifier(schema)
        self._conn.execute(_ddl(schema))

    def close(self) -> None:
        self._conn.close()

    def _q(self, text: str) -> sql.Composed:
        return sql.SQL(text).format(s=self._s)

    def version(self, stream: str) -> int:
        return self._conn.execute(self._q("SELECT COALESCE(MAX(version), 0) FROM {s}.events WHERE stream=%s"),
                                  (stream,)).fetchone()[0]

    def append(self, stream: str, expected_version: int, events: list[Event]) -> list[Event]:
        out = [replace(e, version=expected_version + i + 1) for i, e in enumerate(events)]
        try:
            with self._conn.transaction():
                cur = self._conn.execute(self._q("SELECT COALESCE(MAX(version), 0) FROM {s}.events WHERE stream=%s"),
                                         (stream,))
                at = cur.fetchone()[0]
                if at != expected_version:
                    raise ConcurrencyError(f"{stream}: expected v{expected_version}, at v{at}")
                with self._conn.cursor() as c:
                    c.executemany(self._q("INSERT INTO {s}.events (stream, version, body) VALUES (%s, %s, %s)"),
                                  [(stream, e.version, event_to_json(e)) for e in out])
        except psycopg.errors.UniqueViolation as exc:
            raise ConcurrencyError(str(exc)) from exc
        return out

    def read(self, stream: str) -> list[Event]:
        rows = self._conn.execute(self._q("SELECT body::text FROM {s}.events WHERE stream=%s ORDER BY version"),
                                  (stream,))
        return [event_from_json(r[0]) for r in rows]

    def append_attempt(self, event: Event) -> None:
        self._conn.execute(self._q("INSERT INTO {s}.attempts (stream, body) VALUES (%s, %s)"),
                           (event.stream, event_to_json(event)))

    def read_attempts(self, stream: str) -> list[Event]:
        rows = self._conn.execute(self._q("SELECT body::text FROM {s}.attempts WHERE stream=%s ORDER BY seq"),
                                  (stream,))
        return [event_from_json(r[0]) for r in rows]

    def streams(self) -> list[str]:
        rows = self._conn.execute(self._q("SELECT stream FROM {s}.events GROUP BY stream ORDER BY MIN(seq)"))
        return [r[0] for r in rows]

    def claim(self, key: tuple[Any, ...]):
        k = key_to_text(key)
        row = self._conn.execute(self._q("INSERT INTO {s}.idempotency (key, outcome) VALUES (%s, NULL) "
                                         "ON CONFLICT (key) DO NOTHING RETURNING key"), (k,)).fetchone()
        if row is not None:
            return None
        got = self._conn.execute(self._q("SELECT outcome::text FROM {s}.idempotency WHERE key=%s"), (k,)).fetchone()
        if got is None:
            return self.claim(key)
        return "pending" if got[0] is None else outcome_from_json(got[0])

    def remember(self, key: tuple[Any, ...], outcome: Outcome) -> None:
        self._conn.execute(self._q("UPDATE {s}.idempotency SET outcome=%s WHERE key=%s"),
                           (outcome_to_json(outcome), key_to_text(key)))

    def release(self, key: tuple[Any, ...]) -> None:
        self._conn.execute(self._q("DELETE FROM {s}.idempotency WHERE key=%s AND outcome IS NULL"),
                           (key_to_text(key),))
