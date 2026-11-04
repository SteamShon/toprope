"""Structural validation of a declaration (the first change check, ADR-0009).

Returns issues instead of raising, so a change report can list all of them at once.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..expr import ParseError, Path, parse, paths_read
from .models import ActorRule, ByRole, Deny, Domain, Target

RESERVED_CELLS = {"n/a", "undecided"}
ROOTS = {"target", "actor", "params", "new"}


@dataclass(frozen=True)
class Issue:
    code: str      # e.g. unknown-object, unknown-state, parse-error
    where: str     # dotted location in the declaration
    message: str
    severity: str = "error"  # error | warning


def _states(d: Domain, obj: str) -> set[str] | None:
    tr = d.transitions.get(obj)
    if tr is None:
        return None
    prop = d.objects.get(obj).properties.get(tr.field) if obj in d.objects else None
    return set(prop.enum) if prop and prop.enum else None


def _resolve(d: Domain, obj: str, attrs: tuple[str, ...]) -> str | None:
    """Follow a path's attributes from an object type; return an error message or None."""
    cur = obj
    for i, a in enumerate(attrs):
        if cur not in d.objects:
            return None
        o = d.objects[cur]
        if a in o.properties:
            if i != len(attrs) - 1:
                return f"'{a}' is a property of {cur}; it has no attribute '{attrs[i + 1]}'"
            return None
        link = next((n for n, l in d.links.items() if n == a and l.from_ == cur), None)
        if link is None:
            return f"{cur} has no property or link '{a}'"
        cur = d.links[link].to
    return None


def _check_expr(d: Domain, src: str, where: str, obj: str | None, params: set[str]) -> list[Issue]:
    try:
        node = parse(src)
    except ParseError as e:
        return [Issue("parse-error", where, str(e))]
    out = []
    for p in paths_read(node):
        if p.root not in ROOTS:
            out.append(Issue("unknown-root", where, f"unknown root '{p.root}' in {src!r}"))
        elif p.root in ("target", "new") and obj and p.attrs:
            msg = _resolve(d, obj, p.attrs)
            if msg:
                out.append(Issue("unknown-path", where, f"{p.dotted()}: {msg}"))
        elif p.root == "params" and p.attrs and p.attrs[0] not in params:
            out.append(Issue("unknown-param", where, f"{p.dotted()}: no such param"))
    return out


def validate_domain(d: Domain) -> list[Issue]:
    issues: list[Issue] = []
    add = issues.append
    roles = set(d.roles)

    for name, link in d.links.items():
        for end in (link.from_, link.to):
            if end not in d.objects:
                add(Issue("unknown-object", f"links.{name}", f"unknown object '{end}'"))

    for name, a in d.actions.items():
        where = f"actions.{name}"
        if a.object_type not in d.objects:
            add(Issue("unknown-object", where, f"unknown object '{a.object_type}'"))
        for r in a.actor:
            role = r.role if isinstance(r, ActorRule) else r
            if roles and role not in roles:
                add(Issue("unknown-role", where, f"unknown role '{role}'"))
            if isinstance(r, ActorRule) and r.where:
                issues += _check_expr(d, r.where, f"{where}.actor", a.object_type, set(a.params))
        ids = [p.id for p in a.preconditions]
        if len(ids) != len(set(ids)):
            add(Issue("duplicate-id", where, "precondition ids must be unique"))
        for p in a.preconditions:
            issues += _check_expr(d, p.check, f"{where}.preconditions.{p.id}", a.object_type, set(a.params))
        for e in a.effects:
            for key, value in (e.set or {}).items():
                attr = key.split(".", 1)[1] if key.startswith(("target.", "new.")) else key
                msg = _resolve(d, a.object_type, tuple(attr.split("."))) if a.object_type in d.objects else None
                if msg:
                    add(Issue("unknown-path", f"{where}.effects", f"{key}: {msg}"))
                if isinstance(value, str):  # effect values are check-language expressions
                    issues += _check_expr(d, value, f"{where}.effects.{key}", a.object_type, set(a.params))
        states = _states(d, a.object_type)
        if a.applies_in and states is not None:
            for s in a.applies_in:
                if s not in states:
                    add(Issue("unknown-state", f"{where}.applies_in", f"unknown state '{s}'"))

    for obj, tr in d.transitions.items():
        where = f"transitions.{obj}"
        if obj not in d.objects:
            add(Issue("unknown-object", where, f"unknown object '{obj}'"))
            continue
        prop = d.objects[obj].properties.get(tr.field)
        if prop is None or not prop.enum:
            add(Issue("bad-state-field", where, f"'{tr.field}' must be an enum property of {obj}"))
            continue
        states = set(prop.enum)
        if tr.initial and tr.initial not in states:
            add(Issue("unknown-state", where, f"initial state '{tr.initial}' is not in {sorted(states)}"))
        for state, cells in tr.matrix.items():
            if state not in states:
                add(Issue("unknown-state", f"{where}.matrix.{state}", f"unknown state '{state}'"))
            for action, cell in cells.items():
                cw = f"{where}.matrix.{state}.{action}"
                if action not in d.actions:
                    add(Issue("unknown-action", cw, f"unknown action '{action}'"))
                elif d.actions[action].object_type != obj:
                    add(Issue("wrong-object", cw, f"action '{action}' targets {d.actions[action].object_type}, not {obj}"))
                if isinstance(cell, ByRole):
                    targets = [c for c in cell.by_role.values() if isinstance(c, str)]
                    for role in cell.by_role:
                        if roles and role not in roles:
                            add(Issue("unknown-role", cw, f"unknown role '{role}'"))
                else:
                    targets = [cell.to] if isinstance(cell, Target) else ([] if isinstance(cell, Deny) else [cell])
                for target in targets:
                    if target not in RESERVED_CELLS and target not in states:
                        add(Issue("unknown-state", cw, f"target state '{target}' is not in {sorted(states)}"))
        missing = [s for s in sorted(states) if s not in tr.matrix]
        if missing:
            add(Issue("missing-row", where, f"no matrix row for states {missing} (treated as undecided)", "warning"))
        # Only actions on an existing object (`target`) have a cell per source state. Actions
        # that `create` the object have no source state, so they are not matrix columns.
        obj_actions = sorted(n for n, a in d.actions.items() if a.target == obj)
        for state in sorted(set(tr.matrix) & states):
            absent = [a for a in obj_actions if a not in tr.matrix[state]]
            if absent:
                add(Issue("missing-cell", f"{where}.matrix.{state}",
                          f"no cell for {absent} (treated as undecided: denied and listed)", "warning"))

    for inv in d.invariants:
        where = f"invariants.{inv.id}"
        if inv.on not in d.objects:
            add(Issue("unknown-object", where, f"unknown object '{inv.on}'"))
        issues += _check_expr(d, inv.check, where, inv.on if inv.on in d.objects else None, set())
    ids = [i.id for i in d.invariants]
    if len(ids) != len(set(ids)):
        add(Issue("duplicate-id", "invariants", "invariant ids must be unique"))

    seen: set[str] = set()
    for i, fx in enumerate(d.world.fixtures):
        if len(fx) != 1:
            add(Issue("bad-fixture", f"world.fixtures[{i}]", "a fixture has exactly one object type key"))
            continue
        ((obj, data),) = fx.items()
        if obj not in d.objects:
            add(Issue("unknown-object", f"world.fixtures[{i}]", f"unknown object '{obj}'"))
        fid = data.get("id")
        if not fid:
            add(Issue("bad-fixture", f"world.fixtures[{i}]", "a fixture needs an id"))
        elif fid in seen:
            add(Issue("duplicate-id", f"world.fixtures[{i}]", f"duplicate fixture id '{fid}'"))
        seen.add(fid)

    for sc in d.scenarios:
        for j, st in enumerate(sc.steps):
            if st.do and st.do not in d.actions:
                add(Issue("unknown-action", f"scenarios.{sc.id}.steps[{j}]", f"unknown action '{st.do}'"))
            role = st.actor.get("role")
            if role and roles and role not in roles:
                add(Issue("unknown-role", f"scenarios.{sc.id}.steps[{j}]", f"unknown role '{role}'"))
    return issues
