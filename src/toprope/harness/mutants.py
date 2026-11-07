"""Harness mutants: a check never seen failing proves nothing.

Each mutant is the declaration with one seeded break, given to the execution level only. The
model level and every expectation still read the real declaration, so the mutant stands for an
implementation that drifted from it: a skipped precondition, a wrong transition, a missing role
check, a dropped effect. The harness must report a finding for each one ("killed"). A mutant
that survives is a break the harness cannot see: a precondition no case makes false, a cell no
case reaches, an effect no check reads. `run_mutants` reports survivors; `toprope-harness
--mutants` exits 1 on one. A survivor can be equivalent to the declaration in every state the
harness can build; then say so where the domain's harness results are reviewed.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ..decl.models import ActorRule, Deny, Domain, Target


@dataclass(frozen=True)
class Mutant:
    id: str                 # <operator>:<where>
    description: str        # the seeded break, in domain words
    implementation: Domain


def _raw(d: Domain) -> dict[str, Any]:
    return d.model_dump(by_alias=True, exclude_none=True)


def _to(c: Any) -> str | None:
    if isinstance(c, Target):
        return c.to
    return c if isinstance(c, str) and c not in ("n/a", "undecided") else None


def mutants(d: Domain) -> Iterator[Mutant]:
    """Every single-break mutant of the declaration, in a fixed order."""
    base = _raw(d)

    def make(mid: str, text: str, change) -> Mutant | None:
        raw = copy.deepcopy(base)
        change(raw)
        try:
            return Mutant(mid, text, Domain.model_validate(raw))
        except ValueError:            # the break is not expressible as a declaration
            return None

    out: list[Mutant | None] = []
    for name, a in d.actions.items():
        for k, p in enumerate(a.preconditions):
            out.append(make(f"skip-precondition:{name}.{p.id}", f"{name} does not check {p.id}",
                            lambda r, n=name, k=k: r["actions"][n]["preconditions"].pop(k)))
        roles = [r.role if isinstance(r, ActorRule) else r for r in a.actor]
        if len(roles) > 1:
            for k, role in enumerate(roles):
                out.append(make(f"drop-role:{name}.{role}", f"{role} may no longer {name}",
                                lambda r, n=name, k=k: r["actions"][n]["actor"].pop(k)))
        for k, e in enumerate(a.effects):
            for key in e.set or {}:
                out.append(make(f"skip-effect:{name}.{key}", f"{name} does not set {key}",
                                lambda r, n=name, k=k, key=key: r["actions"][n]["effects"][k]["set"].pop(key)))
    for obj, tr in d.transitions.items():
        states = list(tr.matrix)
        for state, cells in tr.matrix.items():
            for action, c in cells.items():
                cell = ["transitions", obj, "matrix", state, action]
                to = _to(c)
                if to is not None:
                    out.append(make(f"deny-cell:{obj}.{state}.{action}", f"{action} is refused in {state}",
                                    lambda r, cell=cell: _set(r, cell, {"deny": "Refused by a mutant."})))
                    other = next((s for s in states if s != to), None)
                    if other is not None:
                        out.append(make(f"retarget-cell:{obj}.{state}.{action}",
                                        f"{action} in {state} leads to {other}, not {to}",
                                        lambda r, cell=cell, other=other: _set(r, cell, other)))
                elif isinstance(c, Deny):
                    out.append(make(f"allow-cell:{obj}.{state}.{action}", f"{action} is allowed in {state}",
                                    lambda r, cell=cell, state=state: _set(r, cell, state)))
    yield from (m for m in out if m is not None)


def _set(raw: dict[str, Any], path: list[str], value: Any) -> None:
    node = raw
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def run_mutants(d: Domain, *, limit: int | None = None, **harness_kw: Any) -> dict[str, Any]:
    """Run the harness once per mutant (model and execution levels, no exploration or races, so
    each run is fast and reproducible) and report which mutants it killed."""
    from .run import Harness
    killed, survived = [], []
    for k, m in enumerate(mutants(d)):
        if limit is not None and k >= limit:
            break
        r = Harness(d, levels=("model", "execution"), implementation=m.implementation, **harness_kw).run(
            explore_examples=0, races=False)
        row = {"mutant": m.id, "break": m.description}
        if r.ok:
            survived.append(row)
        else:
            row["caught_by"] = sorted({f.kind for f in r.findings})
            killed.append(row)
    total = len(killed) + len(survived)
    return {"total": total, "killed": killed, "survived": survived,
            "score": round(len(killed) / total, 3) if total else None}


__all__ = ["Mutant", "mutants", "run_mutants"]
