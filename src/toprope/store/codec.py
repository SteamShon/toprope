"""JSON encoding of events and outcomes, shared by every store (including memory, for parity).

Tags are unambiguous: datetimes become {"$dt": iso}, dates {"$date": iso}, and any user key
starting with "$" is escaped as "$$...". Tuples become lists. NaN/Infinity and NUL characters
are refused, because PostgreSQL JSONB cannot store them; commands carrying them are rejected
earlier, at command validation.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, fields
from datetime import date, datetime
from typing import Any

from ..types import Event, Outcome

_EVENT_FIELDS = {f.name for f in fields(Event)}


class CodecError(ValueError):
    pass


def _enc(o: Any) -> Any:
    if isinstance(o, datetime):
        return {"$dt": o.isoformat()}
    if isinstance(o, date):
        return {"$date": o.isoformat()}
    if isinstance(o, dict):
        return {("$" + k if isinstance(k, str) and k.startswith("$") else k): _enc(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_enc(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        raise CodecError("NaN/Infinity cannot be stored")
    if isinstance(o, str) and "\x00" in o:
        raise CodecError("NUL characters cannot be stored")
    if o is None or isinstance(o, (str, int, float, bool)):
        return o
    raise CodecError(f"cannot store {type(o).__name__}")


def _dec(o: Any) -> Any:
    if isinstance(o, dict):
        if set(o) == {"$dt"}:
            return datetime.fromisoformat(o["$dt"])
        if set(o) == {"$date"}:
            return date.fromisoformat(o["$date"])
        return {(k[1:] if k.startswith("$$") else k): _dec(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_dec(v) for v in o]
    return o


def dumps(obj: Any) -> str:
    return json.dumps(_enc(obj), sort_keys=True, separators=(",", ":"), allow_nan=False)


def loads(text: str) -> Any:
    return _dec(json.loads(text))


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
