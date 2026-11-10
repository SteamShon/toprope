"""Built-in extractors (ADR-0051): OpenAPI, SQL DDL, a workflow export. Others plug in through
`toprope.extractors`. Each turns one format into candidates citing their exact place."""
from __future__ import annotations

import re
from typing import Any

from ...errors import fixed
from ..port import Candidate, Extraction, Profile

TYPES = {"string": "string", "integer": "integer", "number": "number", "boolean": "boolean"}


def snake(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)).strip("_").lower()
    return s if s and s[0].isalpha() else f"x_{s}"


def pascal(name: str) -> str:
    s = "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", name) if w)
    return s if s and s[0].isalpha() else f"X{s}"


def a_(w: str) -> str:
    return f"{'an' if w[:1].lower() in 'aeiou' else 'a'} {w}"


def singular(name: str) -> str:
    """`orders` → `order`, `statuses` → `status`, `categories` → `category`."""
    low = name.lower()
    if low.endswith("ies") and len(name) > 3:
        return name[:-3] + "y"
    if low.endswith(("sses", "shes", "ches", "xes", "uses")):
        return name[:-2]
    if low.endswith("s") and not low.endswith(("ss", "us", "is")):
        return name[:-1]
    return name


def ignored(profile: Profile, *names: str) -> bool:
    """By the source's name or ours (ADR-0051: a profile may name either)."""
    return any(n in profile.ignore for n in names)


def put(facts: dict[str, Any], key: str, value: Any, out: Extraction, where: str) -> None:
    """Two source names that read as one fact are a conflict, not a silent overwrite."""
    if key in facts:
        out.conflicts.append(f"{where}: two facts read as `{key}`; kept the first")
    else:
        facts[key] = value


def mapping(doc: Any, ref: str, kind: str) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise SystemExit(fixed(f"{ref} is not {kind}: its top level is a {type(doc).__name__}, not a mapping",
                               f"give the {kind} document itself"))
    return doc


def stages(out: Extraction, obj: str, field: str, states: list[str], ref: str) -> None:
    out.candidates.append(Candidate(f"transitions.{obj}", {"field": field, "initial": states[0],
                                                           "matrix": {s: {} for s in states}}, ref))


from .openapi import OpenAPIExtractor
from .sql import SQLExtractor
from .workflow import WorkflowExtractor

BUILTIN = [OpenAPIExtractor(), SQLExtractor(), WorkflowExtractor()]

__all__ = ["BUILTIN", "TYPES", "Any", "Candidate", "Extraction", "Profile", "a_", "ignored", "mapping", "pascal", "put",
           "singular", "snake", "stages"]
