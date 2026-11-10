"""Start a declaration from what a team already has (ADR-0049 A1, ADR-0051).

    from toprope.importers import import_source
    out = import_source("openapi", "api.yaml", domain="shop")        # reader "file" by default
    out["draft"], out["questions"], out["conflicts"]

A Reader reaches the source, an Extractor reads its format, a Profile carries what varies between
teams; all three are ports (see `port.py`), so a new source plugs in without changing Toprope.
Every element of the draft is `proposed`, citing its exact place; a person confirms it (ADR-0041).
"""
from __future__ import annotations

from typing import Any

from ..errors import fixed
from .draft import build
from .port import (
    Candidate,
    Extraction,
    Profile,
    Raw,
    extractor,
    kinds,
    reader,
    register_extractor,
    register_reader,
)


def import_source(kind: str, location: str, *, domain: str = "imported", profile: Profile | None = None,
                  via: str = "file") -> dict[str, Any]:
    profile = profile or Profile()
    raw = reader(via).read(location, profile)
    ext = extractor(kind).extract(raw, profile)
    draft = build(domain, ext)
    _check(draft, kind)
    return {"draft": draft, "questions": ext.questions, "conflicts": ext.conflicts, "candidates": len(ext.candidates)}


def _check(draft: dict[str, Any], kind: str) -> None:
    """A draft that does not validate is never handed on as if it did (ADR-0051)."""
    from pydantic import ValidationError

    from ..decl import Domain, validate_domain
    try:
        errors = [str(i) for i in validate_domain(Domain.model_validate(draft)) if i.severity == "error"]
    except ValidationError as e:
        errors = [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
    if errors:
        raise SystemExit(fixed(f"the {kind} extractor made a draft that does not validate: {'; '.join(errors[:5])}",
                               "report it to the extractor's author; meanwhile a profile's `ignore` can leave the "
                               "named part out"))


__all__ = ["Candidate", "Extraction", "Profile", "Raw", "import_source", "kinds", "register_extractor",
           "register_reader"]
