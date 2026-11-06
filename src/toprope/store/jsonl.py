"""An event store kept as append-only JSON lines in a directory (ADR-0037).

It is meant to be committed to git, like the domain commit store: the self domains' events
(answers, confirmations, requests) are decisions, shared and audited through git. Files:

  events.jsonl       one line per appended event: {"stream", "event"}
  attempts.jsonl     one line per denied or refused attempt
  idempotency.jsonl  one line per claim, outcome or release of an idempotency key

Every operation takes an exclusive file lock and re-reads the files, so several processes
on one checkout stay consistent. Lines are only ever appended, and each write is fsync'd.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..types import Event, Outcome
from . import ConcurrencyError, EventStore
from .codec import event_from_json, event_to_json, outcome_from_json, outcome_to_json


class JSONLEventStore(EventStore):
    def __init__(self, path: str | Path):
        self.root = Path(path)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self):
        with open(self.root / ".lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _lines(self, name: str) -> list[dict[str, Any]]:
        p = self.root / name
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]

    def _append(self, name: str, entries: list[dict[str, Any]]) -> None:
        with open(self.root / name, "a") as f:
            f.write("".join(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n" for e in entries))
            f.flush()
            os.fsync(f.fileno())

    def _events(self, stream: str) -> list[str]:
        return [e["event"] for e in self._lines("events.jsonl") if e["stream"] == stream]

    # -- streams ---------------------------------------------------------------------------
    def version(self, stream: str) -> int:
        with self._lock():
            return len(self._events(stream))

    def append(self, stream: str, expected_version: int, events: list[Event]) -> list[Event]:
        with self._lock():
            at = len(self._events(stream))
            if at != expected_version:
                raise ConcurrencyError(f"{stream}: expected v{expected_version}, at v{at}")
            out = [replace(e, version=expected_version + i + 1) for i, e in enumerate(events)]
            encoded = [event_to_json(e) for e in out]          # encode all first: all-or-nothing
            self._append("events.jsonl", [{"stream": stream, "event": t} for t in encoded])
            return [event_from_json(t) for t in encoded]

    def read(self, stream: str) -> list[Event]:
        with self._lock():
            return [event_from_json(t) for t in self._events(stream)]

    def append_attempt(self, event: Event) -> None:
        with self._lock():
            self._append("attempts.jsonl", [{"stream": event.stream, "event": event_to_json(event)}])

    def read_attempts(self, stream: str) -> list[Event]:
        with self._lock():
            return [event_from_json(e["event"]) for e in self._lines("attempts.jsonl") if e["stream"] == stream]

    def streams(self) -> list[str]:
        with self._lock():
            return list(dict.fromkeys(e["stream"] for e in self._lines("events.jsonl")))

    # -- idempotency -----------------------------------------------------------------------
    def _state(self, key: tuple[Any, ...]) -> str | None:
        k = json.dumps(list(key), default=str)
        state = None
        for e in self._lines("idempotency.jsonl"):
            if e["key"] == k:
                state = None if e["state"] == "released" else e["state"]
        return state

    def claim(self, key):
        with self._lock():
            state = self._state(key)
            if state is not None:
                return "pending" if state == "pending" else outcome_from_json(state)
            self._append("idempotency.jsonl", [{"key": json.dumps(list(key), default=str), "state": "pending"}])
            return None

    def remember(self, key, outcome: Outcome) -> None:
        with self._lock():
            self._append("idempotency.jsonl", [{"key": json.dumps(list(key), default=str),
                                                "state": outcome_to_json(outcome)}])

    def release(self, key) -> None:
        with self._lock():
            if self._state(key) == "pending":                   # never forget a finished outcome
                self._append("idempotency.jsonl", [{"key": json.dumps(list(key), default=str),
                                                    "state": "released"}])

    def close(self) -> None:
        pass


__all__ = ["JSONLEventStore"]
