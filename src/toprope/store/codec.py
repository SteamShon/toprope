"""JSON encoding of events and outcomes for durable stores."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from typing import Any

from ..types import Event, Outcome

_EVENT_FIELDS = {f.name for f in fields(Event)}


def _default(o: Any) -> Any:
    if isinstance(o, datetime):
        return {"__dt__": o.isoformat()}
    raise TypeError(f"cannot encode {type(o).__name__}")


def _hook(d: dict) -> Any:
    if set(d) == {"__dt__"}:
        return datetime.fromisoformat(d["__dt__"])
    return d


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=_default, sort_keys=True, separators=(",", ":"))


def loads(text: str) -> Any:
    return json.loads(text, object_hook=_hook)


def event_to_json(e: Event) -> str:
    return dumps(asdict(e))


def event_from_json(text: str) -> Event:
    d = loads(text)
    return Event(**{k: v for k, v in d.items() if k in _EVENT_FIELDS})


def outcome_to_json(o: Outcome) -> str:
    return dumps({"status": o.status, "code": o.code, "reason": o.reason, "state": o.state,
                  "events": [asdict(e) for e in o.events]})


def outcome_from_json(text: str) -> Outcome:
    d = loads(text)
    return Outcome(d["status"], d["code"], d["reason"], d["state"],
                   tuple(Event(**{k: v for k, v in e.items() if k in _EVENT_FIELDS}) for e in d["events"]))


def key_to_text(key: tuple[Any, ...]) -> str:
    return dumps(list(key))
