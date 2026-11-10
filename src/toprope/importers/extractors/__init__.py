"""Built-in extractors (ADR-0051): OpenAPI, SQL DDL, a workflow export. Others plug in through
`toprope.extractors`. Each turns one format into candidates citing their exact place."""
from __future__ import annotations

import re
from typing import Any

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


def stages(out: Extraction, obj: str, field: str, states: list[str], ref: str) -> None:
    out.candidates.append(Candidate(f"transitions.{obj}", {"field": field, "initial": states[0],
                                                           "matrix": {s: {} for s in states}}, ref))


from .openapi import OpenAPIExtractor
from .sql import SQLExtractor
from .workflow import WorkflowExtractor

BUILTIN = [OpenAPIExtractor(), SQLExtractor(), WorkflowExtractor()]

__all__ = ["BUILTIN", "TYPES", "Any", "Candidate", "Extraction", "Profile", "a_", "pascal", "snake", "stages"]
