"""Structural validation of a declaration (the first change check, ADR-0009).

Returns issues instead of raising, so a change report can list all of them at once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..expr import ParseError, Path, parse, paths_read
from .models import (
    RESERVED_ACTORS,
    ActorRule,
    ByRole,
    Deny,
    Domain,
    RuleCheck,
    RuleRoles,
    Target,
)

RESERVED_CELLS = {"n/a", "undecided"}
ROOTS = {"target", "actor", "params", "new"}


# Every action surface (MCP tools, generated UI) carries these besides the declared params.
RESERVED_PARAMS = frozenset({"target_id", "new_id", "idempotency_key", "thread_id", "run_id"})
# Params are read in expressions as `params.<name>`, so a name is an expression identifier.
PARAM_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


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
        if a == "id":                      # every object has its id (the stream it lives in)
            if i != len(attrs) - 1:
                return f"'id' of {cur} is a string; it has no attribute '{attrs[i + 1]}'"
            return None
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


def _rules(d: Domain) -> list[Issue]:
    """Outcome rules (ADR-0048): each names a state or a property of a declared object, its roles
    are declared, and it covers at least one action."""
    from .rules import reaches
    out: list[Issue] = []
    for rid, r in d.rules.items():
        where = f"rules.{rid}"
        obj, _, part = r.on.partition(".")
        tr = d.transitions.get(obj)
        states = set(tr.matrix) | ({tr.initial} if tr and tr.initial else set()) if tr else set()
        props = set(d.objects[obj].properties) if obj in d.objects else set()
        if obj not in d.objects or not part:
            out.append(Issue("unknown-object", where, f"`on` names <Object>.<state or property>: '{r.on}'"))
            continue
        if part not in states and part not in props:
            out.append(Issue("unknown-path", where, f"{obj} has no state or property '{part}'"))
            continue
        froms = list(tr.matrix) if tr else [None]
        covered = [a for a in d.actions if any(r.on in reaches(d, a, f) for f in froms + [None])]
        if isinstance(r.requires, RuleRoles):
            for role in r.requires.roles:
                if d.roles and role not in d.roles:
                    out.append(Issue("unknown-role", where, f"unknown role '{role}'"))
        elif isinstance(r.requires, RuleCheck):      # read with the params of every action it covers
            params = {p for a in covered for p in d.actions[a].params}
            out += _check_expr(d, r.requires.check, f"{where}.requires.check", obj, params)
        if not covered:
            out.append(Issue("rule-covers-nothing", where, f"no action reaches {r.on}", "warning"))
    return out


def validate_domain(d: Domain) -> list[Issue]:
    issues: list[Issue] = []
    add = issues.append
    roles = set(d.roles)

    issues += _rules(d)

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
            if roles and role not in roles and role not in RESERVED_ACTORS:
                add(Issue("unknown-role", where, f"unknown role '{role}'"))
            if isinstance(r, ActorRule) and r.where:
                issues += _check_expr(d, r.where, f"{where}.actor", a.object_type, set(a.params))
        if a._declared_rationale:
            add(Issue("reserved-param", f"{where}.params.rationale",
                      "'rationale' is reserved on a decision action: every one takes it (ADR-0041)"))
        for pname in a.params:
            if pname in RESERVED_PARAMS:
                add(Issue("reserved-param", f"{where}.params.{pname}",
                          f"'{pname}' is reserved for every action's own arguments: {sorted(RESERVED_PARAMS)}"))
            elif not PARAM_NAME.fullmatch(pname):
                add(Issue("invalid-param-name", f"{where}.params.{pname}",
                          "a param name is letters, digits and underscores, not starting with a digit"))
        ids = [p.id for p in a.preconditions]
        if len(ids) != len(set(ids)):
            add(Issue("duplicate-id", where, "precondition ids must be unique"))
        for p in a.preconditions:
            issues += _check_expr(d, p.check, f"{where}.preconditions.{p.id}", a.object_type, set(a.params))
        roles_named = {r.role if isinstance(r, ActorRule) else r for r in a.actor}
        if "external:kernel" in roles_named and roles_named - {"external:kernel"}:
            add(Issue("mixed-external", f"{where}.actor",
                      "an action is either for `external:kernel` or for others: declare two actions"))
        for k, e in enumerate(a.effects):
            if e.call is not None:
                issues += _check_call(d, name, a, k, e)
                continue
            if e.create is not None:
                add(Issue("unsupported-effect", f"{where}.effects", f"create effects are not supported yet ({e.create})"))
            for key, value in (e.set or {}).items():
                if key.startswith("new.") and a.creates is None:
                    add(Issue("unsupported-effect", f"{where}.effects", f"{key}: `new.` is only valid in a create action"))
                attr = key.split(".", 1)[1] if key.startswith(("target.", "new.")) else key
                msg = _resolve(d, a.object_type, tuple(attr.split("."))) if a.object_type in d.objects else None
                if msg:
                    add(Issue("unknown-path", f"{where}.effects", f"{key}: {msg}"))
                if isinstance(value, str):  # effect values are check-language expressions
                    issues += _check_expr(d, value, f"{where}.effects.{key}", a.object_type, set(a.params))
        if a.creates is not None and a.creates in d.objects:
            issues += _unset_on_create(d, name, a, where)
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
    for name, h in d.handoffs.items():
        where = f"handoffs.{name}"
        a = d.actions.get(h.when.action)
        if a is None:
            add(Issue("unknown-action", f"{where}.when", f"unknown action '{h.when.action}'"))
            continue
        obj = a.object_type
        issues += _check_expr(d, h.target, f"{where}.target", obj, set(a.params))
        for p, src in h.params.items():
            issues += _check_expr(d, src, f"{where}.params.{p}", obj, set(a.params))

    return issues


def check_handoffs(sender: Domain, published: dict[str, tuple[Domain, int]]) -> list[Issue]:
    """The compile-time contract of each handoff against the receiving domain's published
    interface (ADR-0022). `published` maps a domain name to (its declaration, its interface
    major version). A removal or rename on the receiving side breaks the handoff here."""
    out: list[Issue] = []
    for name, h in sender.handoffs.items():
        where = f"handoffs.{name}"
        pub = published.get(h.to.domain)
        if pub is None:
            out.append(Issue("unknown-domain", f"{where}.to", f"no published domain '{h.to.domain}'"))
            continue
        recv, major = pub
        want = int(h.to.interface.split(".")[0])
        if want != major:
            out.append(Issue("interface-major", f"{where}.to",
                             f"targets {h.to.domain} {h.to.interface}, published interface is {major}.x"))
        ra = recv.actions.get(h.to.action)
        if ra is None:
            out.append(Issue("unknown-action", f"{where}.to", f"{h.to.domain} has no action '{h.to.action}'"))
            continue
        roles = {r.role if isinstance(r, ActorRule) else r for r in ra.actor}
        if "system" not in roles:
            out.append(Issue("handoff-actor", f"{where}.to",
                             f"{h.to.domain}.{h.to.action} must allow `system` in its actor rule"))
        if ra.requires == "human":
            out.append(Issue("handoff-actor", f"{where}.to",
                             f"{h.to.domain}.{h.to.action} requires a person; a handoff acts as `system`"))
        for p in h.params:
            if p not in ra.params:
                out.append(Issue("unknown-param", f"{where}.params.{p}", f"{h.to.domain}.{h.to.action} has no param '{p}'"))
        for p, spec in ra.params.items():
            if not spec.optional and p not in h.params:
                out.append(Issue("missing-param", f"{where}.params", f"{h.to.domain}.{h.to.action} requires '{p}'"))
            elif p in h.params and (t := _static_type(sender, h, p)) and not _compatible(t, spec):
                out.append(Issue("param-type", f"{where}.params.{p}",
                                 f"maps a {t} to {h.to.domain}.{h.to.action}.{p}"))
    return out


def _static_type(d: Domain, h, param: str) -> str | None:
    """The type of a mapping that is a literal or a direct property path, when known."""
    try:
        node = parse(h.params[param])
    except ParseError:
        return None
    from ..expr.ast import Literal as Lit
    if isinstance(node, Lit):
        v = node.value
        return ("boolean" if isinstance(v, bool) else "integer" if isinstance(v, int)
                else "number" if isinstance(v, float) else "string" if isinstance(v, str) else None)
    if isinstance(node, Path) and node.root == "target" and len(node.attrs) == 1:
        a = d.actions.get(h.when.action)
        obj = d.objects.get(a.object_type) if a else None
        prop = obj.properties.get(node.attrs[0]) if obj else None
        if prop is not None:
            return "string" if prop.enum else prop.type
        if node.attrs[0] == "id":
            return "string"
    if isinstance(node, Path) and node.root == "actor" and node.attrs == ("id",):
        return "string"
    return None


def _compatible(t: str, spec) -> bool:
    if spec.many:
        return False
    if spec.ref is not None or spec.enum is not None:
        return t == "string"
    return t == spec.type or (t == "integer" and spec.type == "number")


def _unset_on_create(d: Domain, name: str, a: Any, where: str) -> list[Issue]:
    """A creating action must set every required property: from a required param of the same
    name, or an effect. Otherwise it makes objects without it (#86: Commits without
    `domain_id`). A warning, so a declaration already running with it can still be fixed."""
    tr = d.transitions.get(a.creates)
    set_by_effects = {k.split(".", 1)[1] if k.startswith(("target.", "new.")) else k
                      for e in a.effects for k in (e.set or {})}
    out = []
    for prop, spec in d.objects[a.creates].properties.items():
        if spec.optional or prop == "id" or (tr is not None and prop == tr.field):
            continue
        given = prop in a.params and not a.params[prop].optional
        if not given and prop not in set_by_effects:
            how = "an optional param" if prop in a.params else "nothing"
            out.append(Issue("unset-on-create", f"{where}.params", f"{name} creates a {a.creates} without its "
                             f"required `{prop}` ({how} sets it): make the param required, set it in an "
                             "effect, or make the property optional", severity="warning"))
    return out


def _check_call(d: Domain, name: str, a, k: int, e) -> list[Issue]:
    """A kernel-service call (ADR-0028): the service, its inputs, and the reply action."""
    from ..kernel import CATALOG, KERNEL
    out: list[Issue] = []
    where = f"actions.{name}.effects[{k}]"
    svc = CATALOG.get(e.call)
    if svc is None:
        return [Issue("unknown-service", where, f"no kernel service '{e.call}' (one of {sorted(CATALOG)})")]
    for i in svc.required():
        if i not in e.with_:
            out.append(Issue("missing-input", f"{where}.with", f"{e.call} needs '{i}'"))
    for i, src in e.with_.items():
        if i not in svc.inputs:
            out.append(Issue("unknown-input", f"{where}.with.{i}", f"{e.call} has no input '{i}'"))
        out += _check_expr(d, src, f"{where}.with.{i}", a.object_type, set(a.params))
    r = d.actions.get(e.reply)
    if r is None:
        return out + [Issue("unknown-reply", f"{where}.reply", f"no action '{e.reply}'")]
    if r.creates is not None:
        # A reply may create an object (ADR-0029: a Commit) when the service returns its `id`.
        if "id" not in svc.fields():
            out.append(Issue("reply-target", f"{where}.reply",
                             f"{e.reply} creates an object, but {e.call} returns no `id` for it"))
    elif r.object_type != a.object_type:
        out.append(Issue("reply-target", f"{where}.reply",
                         f"{e.reply} must target {a.object_type}, the object that called {e.call}"))
    if KERNEL not in {x.role if isinstance(x, ActorRule) else x for x in r.actor}:
        out.append(Issue("reply-actor", f"{where}.reply", f"{e.reply} must allow `{KERNEL}`"))
    fields = svc.fields()
    for p, spec in r.params.items():
        if p not in fields:
            out.append(Issue("reply-param", f"actions.{e.reply}.params.{p}",
                             f"{e.call} returns no '{p}' (it returns {sorted(fields)})"))
        elif not _reply_type_ok(spec, fields[p]):
            out.append(Issue("reply-param-type", f"actions.{e.reply}.params.{p}",
                             f"{e.call} returns '{p}' as a {fields[p]}"))
    return out


def _reply_type_ok(spec, field: str) -> bool:
    if field == "strings":
        return spec.many and spec.type == "string" and not (spec.ref or spec.enum)
    return not (spec.many or spec.ref or spec.enum) and spec.type == field
