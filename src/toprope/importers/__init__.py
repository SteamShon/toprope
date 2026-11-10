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
from .draft import Item, apply, build, plan
from .port import (
    Candidate,
    Extraction,
    Note,
    Profile,
    Raw,
    extractor,
    kinds,
    reader,
    register_extractor,
    register_reader,
)


def import_source(kind: str, location: str, *, domain: str = "imported", profile: Profile | None = None,
                  via: str | None = None, into: dict[str, Any] | None = None) -> dict[str, Any]:
    """The draft a source gives, and what it cannot say. `via` defaults to the reader of the same
    name as the extractor if there is one (`mcp`), else `file`. With `into` (an existing draft),
    `items` is what joining the source to it adds (`draft.plan`): the draft's own elements are never
    overwritten, and each disagreement is a conflict naming both places."""
    profile = profile or Profile()
    via = via or ("mcp" if kind == "mcp" else "file")
    raw = reader(via).read(location, profile)
    ext = extractor(kind).extract(raw, profile)
    places: dict[str, str] = {}
    draft = build(domain, ext, places)
    _check(draft, kind)
    out: dict[str, Any] = {"draft": draft, "candidates": len(ext.candidates), "raw": raw, "places": places}
    if into is not None:
        out["items"] = plan(into, draft, places, ext)
    out.update(questions=ext.questions, conflicts=ext.conflicts, question_records=ext.question_records(),
               conflict_records=ext.conflict_records(), binding=ext.binding)
    return out


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


__all__ = ["Candidate", "Extraction", "Item", "Note", "Profile", "Raw", "apply", "import_source", "kinds", "plan",
           "register_extractor", "register_reader"]
