"""The ports an external source plugs into (ADR-0049 A1, ADR-0051).

Bringing a team's existing material into a declaration has two physical parts, kept apart so
each can be replaced without touching Toprope:

- a **Reader** reaches a source where it lives (a file, a URL, an API such as Jira's) and returns
  its bytes, with the ref every candidate's place is written after;
- an **Extractor** reads one format (OpenAPI, SQL DDL, a workflow export, ...) and returns
  **candidates**: element paths with values, each citing its exact place, and the questions the
  source cannot answer.

What varies between teams without new code is a **profile** (a YAML file): which fields are
stages, where roles come from, what to ignore, what to rename.

Plugging in: a package declares entry points in the groups `toprope.readers` and
`toprope.extractors`, each naming a class with a `kind` and the method below; or code calls
`register_reader` / `register_extractor`. Built-ins register the same way.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from ..errors import fixed

READERS_GROUP = "toprope.readers"
EXTRACTORS_GROUP = "toprope.extractors"


@dataclass
class Candidate:
    """One element the source says something about: a declaration path (as `propose_element`
    takes it), the value, and the exact place it came from."""
    path: str
    value: Any
    ref: str


@dataclass
class Extraction:
    candidates: list[Candidate] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)       # two places that disagree, both named


@dataclass
class Raw:
    data: bytes
    ref: str                                                  # e.g. the path or URL, for citations
    parts: list[Raw] | None = None                            # several documents, each with its own ref


@dataclass
class Profile:
    """What varies between teams, as data (ADR-0051)."""
    stage_fields: list[str] = field(default_factory=lambda: ["status", "state", "stage"])
    roles: list[str] = field(default_factory=lambda: ["unassigned"])   # who acts, until the interview says
    roles_from: str | None = None      # an extension naming an operation's roles, e.g. `x-roles`
    ignore: list[str] = field(default_factory=list)                  # source names to leave out
    rename: dict[str, str] = field(default_factory=dict)             # source name -> declared name
    object: str = "Ticket"             # the thing a workflow moves
    options: dict[str, Any] = field(default_factory=dict)            # anything a plugged-in extractor reads

    @classmethod
    def load(cls, path: str | Path | None) -> Profile:
        if path is None:
            return cls()
        try:
            data = yaml.safe_load(Path(path).read_text()) or {}
        except (OSError, yaml.YAMLError) as e:
            raise SystemExit(fixed(f"cannot read the profile {path}: {e}", "give a YAML file of profile keys")) from None
        if not isinstance(data, dict):
            raise SystemExit(fixed(f"the profile {path} is a {type(data).__name__}, not a mapping of keys",
                                   "write `key: value` lines, e.g. `stage_fields: [status]`"))
        known = set(cls.__dataclass_fields__)
        unknown = sorted(set(map(str, data)) - known)
        if unknown:
            raise SystemExit(fixed(f"the profile {path} has unknown key(s) {', '.join(unknown)}",
                                   f"use {', '.join(sorted(known))}; put an extractor's own settings under `options`"))
        shapes = {"stage_fields": list, "roles": list, "ignore": list, "rename": dict, "options": dict,
                  "object": str, "roles_from": (str, type(None))}
        for key, shape in shapes.items():
            v = data.get(key)
            if key in data and not isinstance(v, shape):
                example = {list: f"`{key}: [a, b]`", dict: f"`{key}: {{a: b}}`"}.get(shape, f"`{key}: name`")
                raise SystemExit(fixed(f"the profile {path}: `{key}` is a {type(v).__name__}", f"write it as {example}"))
            if isinstance(v, list) and not all(isinstance(x, str) for x in v):
                raise SystemExit(fixed(f"the profile {path}: `{key}` holds something other than names",
                                       f"write `{key}` as a list of names"))
        return cls(**data)

    def name(self, source_name: str) -> str:
        return self.rename.get(source_name, source_name)


class Reader(Protocol):
    kind: str

    def read(self, location: str, profile: Profile) -> Raw: ...


class Extractor(Protocol):
    kind: str

    def extract(self, raw: Raw, profile: Profile) -> Extraction: ...


_READERS: dict[str, Any] = {}
_EXTRACTORS: dict[str, Any] = {}
_discovered = False


def register_reader(reader: Any) -> None:
    _READERS[reader.kind] = reader


def register_extractor(extractor: Any) -> None:
    _EXTRACTORS[extractor.kind] = extractor


def _discover() -> None:
    """Registered in code wins over an installed package's entry point, which wins over a built-in."""
    global _discovered
    if _discovered:
        return
    _discovered = True
    import sys
    from importlib.metadata import entry_points

    from . import extractors, readers
    for group, table in ((READERS_GROUP, _READERS), (EXTRACTORS_GROUP, _EXTRACTORS)):
        for ep in entry_points(group=group):
            try:
                cls = ep.load()
                plugin = cls() if isinstance(cls, type) else cls
                table.setdefault(plugin.kind, plugin)
            except (Exception, SystemExit) as e:  # noqa: BLE001 - one bad plugin is reported, not fatal
                print(f"warning: the {group} plugin {ep.name} did not load: {e}", file=sys.stderr)
    for r in readers.BUILTIN:
        _READERS.setdefault(r.kind, r)
    for x in extractors.BUILTIN:
        _EXTRACTORS.setdefault(x.kind, x)


def reader(kind: str) -> Any:
    _discover()
    if kind not in _READERS:
        raise SystemExit(fixed(f"no reader {kind!r}", f"use one of {', '.join(sorted(_READERS))}, or install a "
                               f"package that plugs one into `{READERS_GROUP}`"))
    return _READERS[kind]


def extractor(kind: str) -> Any:
    _discover()
    if kind not in _EXTRACTORS:
        raise SystemExit(fixed(f"no extractor {kind!r}", f"use one of {', '.join(sorted(_EXTRACTORS))}, or install "
                               f"a package that plugs one into `{EXTRACTORS_GROUP}`"))
    return _EXTRACTORS[kind]


def kinds() -> dict[str, list[str]]:
    _discover()
    return {"readers": sorted(_READERS), "extractors": sorted(_EXTRACTORS)}
