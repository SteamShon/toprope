"""How risky a change is (ADR-0050): computed from the change check, never declared.

A change is low only when it is known to be harmless, never because nothing flagged it (#210's
review). Low needs all of:
- every check ran and passed with no more warnings than the base had, except the natural-language
  check (advisory, ADR-0009) and the in-flight and log-replay checks when nothing is deployed;
- nothing removed;
- every changed element differs only in its wording (`description`, a glossary term) or is a
  narrowing of an action no person-only rule covers (fewer actors, or a new precondition:
  ADR-0050, Resolved 3), and every other added element is a term, a scenario or a fixture;
- the outcome rules and the approval rule unchanged (ADR-0050, Resolved 2).
Anything else is high, with the reasons. A first version is high: there is nothing to compare.
"""
from __future__ import annotations

from typing import Any

from ..decl.interface import review_contents
from ..decl.models import Domain

LOW, HIGH = "low", "high"
WORDING = ("description",)
ADDED_OK = ("term:", "scenario:", "fixture:")
CHANGED_OK = ("term:", "purpose")
MAY_SKIP = {"nl"}                      # advisory; its findings are warnings at most (ADR-0009)


def _without_wording(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _without_wording(v) for k, v in x.items() if k not in WORDING}
    if isinstance(x, list):
        return [_without_wording(v) for v in x]
    return x


def _dump(x: Any) -> Any:
    return x.model_dump(mode="json", by_alias=True, exclude_none=True) if hasattr(x, "model_dump") else x


def _person_only(d: Domain) -> set[str]:
    """Actions a person-only rule covers: `requires: human` on the action, or an outcome rule
    on the object it acts on (ADR-0048). Any change to who may take them is high (Resolved 2)."""
    ruled = {r.on.split(".")[0] for r in d.rules.values()}
    return {n for n, a in d.actions.items() if a.requires == "human" or (a.object_type or "") in ruled
            or (a.creates or "") in ruled}


def _narrower(key: str, old: Any, new: Any, person_only: set[str]) -> bool:
    """An action that now lets fewer actors take it, and is otherwise the same."""
    if not key.startswith("action:") or key[len("action:"):] in person_only:
        return False
    o, n = _without_wording(_dump(old)), _without_wording(_dump(new))
    if not (isinstance(o, dict) and isinstance(n, dict)):
        return False
    oa, na = o.pop("actor", None), n.pop("actor", None)
    return o == n and isinstance(oa, list) and isinstance(na, list) and na != oa \
        and all(x in oa for x in na)


def assess(report: Any, new: Domain, old: Domain | None,
           pending: frozenset[str] = frozenset(),
           base_warnings: dict[str, int] | None = None) -> tuple[str, list[str]]:
    """`pending`: checks allowed not to have run yet because a later check runs them (TLC, which
    the request's own `check_commit` runs in the workflow; its recorded risk is what counts)."""
    if old is None:
        return HIGH, ["a first version: nothing to compare with"]
    reasons: list[str] = []
    for name, res in report.checks.items():
        if not res.ran:
            if name in MAY_SKIP or name in pending or (name in ("in_flight", "log_replay")
                                                       and "nothing deployed" in (res.note or "")):
                continue
            reasons.append(f"the {name} check did not run ({res.note or 'skipped'})")
        elif not res.ok:
            reasons.append(f"the {name} check failed")
        else:
            warned = [p.message for p in res.problems if p.severity == "warning"]
            had = (base_warnings or {}).get(name, 0) if base_warnings is not None else 0
            if len(warned) > had:          # with no record of the base, every warning counts
                reasons.append(f"the {name} check warned {len(warned)} time(s), the base {had}: "
                               + "; ".join(warned)[:300])
    before, after = review_contents(old), review_contents(new)
    removed = sorted(set(before) - set(after))
    if removed:
        reasons.append("removed: " + ", ".join(removed[:5]))
    person_only = _person_only(old) | _person_only(new)
    added = sorted(k for k in set(after) - set(before) if not k.startswith(ADDED_OK)
                   and not (k.startswith("precondition:") and k[len("precondition:"):].split(".")[0] not in person_only))
    if added:
        reasons.append("added: " + ", ".join(added[:5]))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k]
                     and not k.startswith(CHANGED_OK)
                     and _without_wording(_dump(before[k])) != _without_wording(_dump(after[k]))
                     and not _narrower(k, before[k], after[k], person_only))
    if changed:
        reasons.append("changed beyond its wording: " + ", ".join(changed[:5]))
    if {k: _dump(r) for k, r in old.rules.items()} != {k: _dump(r) for k, r in new.rules.items()}:
        reasons.append("an outcome rule changed")
    if _dump(old.approval) != _dump(new.approval):
        reasons.append("the approval rule changed")
    return (HIGH, reasons) if reasons else (LOW, [])


def warnings_of(rows: dict[str, dict[str, Any]]) -> dict[str, int] | None:
    """Warnings per check, from a commit's recorded check rows (`N warning(s)` in the summary)."""
    import re
    if not rows:
        return None
    out = {}
    for name, row in rows.items():
        m = re.search(r"(\d+) warning\(s\)", str(row.get("summary", "")))
        if m:
            out[name] = int(m.group(1))
    return out


def summary(level: str, reasons: list[str]) -> str:
    return level if not reasons else f"{level}: " + "; ".join(reasons)


def parse(summary_text: str) -> tuple[str, list[str]]:
    level, _, rest = (summary_text or "").partition(": ")
    return level.strip(), [r for r in rest.split("; ") if r]
