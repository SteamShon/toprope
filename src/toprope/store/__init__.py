"""The EventStore port and the in-memory adapter (ADR-0012, docs/semantics.md §3, §5)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any, Literal

from ..types import Event, Outcome


class ConcurrencyError(Exception):
    """The stream moved since it was loaded (optimistic concurrency)."""


class EventStore(ABC):
    @abstractmethod
    def version(self, stream: str) -> int: ...

    @abstractmethod
    def append(self, stream: str, expected_version: int, events: list[Event]) -> list[Event]:
        """Append atomically if the stream is at `expected_version`; return events with versions."""

    @abstractmethod
    def read(self, stream: str) -> list[Event]: ...

    @abstractmethod
    def append_attempt(self, event: Event) -> None:
        """Attempts never bump a stream version (docs/semantics.md §2)."""

    @abstractmethod
    def read_attempts(self, stream: str) -> list[Event]: ...

    @abstractmethod
    def streams(self) -> list[str]: ...

    @abstractmethod
    def claim(self, key: tuple[Any, ...]) -> Outcome | Literal["pending"] | None:
        """Atomically claim an idempotency key. Returns the stored outcome if the command already
        finished, "pending" if another call holds the claim, or None if this call now holds it."""

    @abstractmethod
    def remember(self, key: tuple[Any, ...], outcome: Outcome) -> None:
        """Store the final outcome for a claimed key."""

    @abstractmethod
    def release(self, key: tuple[Any, ...]) -> None:
        """Drop a claim without an outcome (a transient failure), so the key can be retried."""


class MemoryEventStore(EventStore):
    def __init__(self) -> None:
        self._streams: dict[str, list[Event]] = {}
        self._attempts: dict[str, list[Event]] = {}
        self._idem: dict[tuple[Any, ...], Outcome | str] = {}

    def version(self, stream: str) -> int:
        return len(self._streams.get(stream, []))

    def append(self, stream: str, expected_version: int, events: list[Event]) -> list[Event]:
        if self.version(stream) != expected_version:
            raise ConcurrencyError(f"{stream}: expected v{expected_version}, at v{self.version(stream)}")
        out = [replace(e, version=expected_version + i + 1) for i, e in enumerate(events)]
        self._streams.setdefault(stream, []).extend(out)
        return out

    def read(self, stream: str) -> list[Event]:
        return list(self._streams.get(stream, []))

    def append_attempt(self, event: Event) -> None:
        self._attempts.setdefault(event.stream, []).append(event)

    def read_attempts(self, stream: str) -> list[Event]:
        return list(self._attempts.get(stream, []))

    def streams(self) -> list[str]:
        return list(self._streams)

    def claim(self, key):
        if key in self._idem:
            return self._idem[key]
        self._idem[key] = "pending"
        return None

    def remember(self, key, outcome: Outcome) -> None:
        self._idem[key] = outcome

    def release(self, key) -> None:
        if self._idem.get(key) == "pending":   # never forget a finished outcome
            del self._idem[key]
