"""Export a declaration's model level to TLA+, for TLC (ADR-0043).

The model starts from one fixture at a time, as an instance (a function from field name to
value): no step or invariant reads another instance, so the instances are independent. It takes a
step whenever an actor (one per role, as the harness names them) may take an action on an
instance with some param values: the actor rules, the matrix cell for the actor's role, the
preconditions, and every `set` effect evaluating. Invariants are checked on every state, with
no guard: a step that breaks one is the finding. Kernel calls and handoffs are outbox events,
outside the state.

Values are tagged, `<<"s", "x">>`, `<<"i", 3>>`, `<<"b", TRUE>>`, `<<"l", <<...>>>>`,
`<<"r", record>>`, `<<"n">>` (null) and `<<"e">>` (an evaluation error), so TLC never compares two
values of different types, and the check language's fail-closed rules hold: an operator on the
wrong type gives `E`, and a check passes only when it gives `<<"b", TRUE>>`.

Creating actions are steps too: each created type gets one fresh id (`new-<Object>`), the empty
world is one more start, and a creating step runs only from it, making one object (its declared
params, its initial state, its `set` effects), so a run still follows one object. A creating
param no expression reads gets one value. The `system` actor a handoff acts as is in the model
when an action is for it.

A link path reads the linked objects from their fixtures, a constant (`Fix_<Object>`): `target.l`
is the linked object or null, a list of them for a link to many. That is sound only for what no
modeled action changes, so a field read through a link must be one no action sets; then the
instances stay independent.

Time is the harness's clock, frozen (replay runs on the same one): `now()` is that instant, an
effect stores it as its ISO string, and every ISO time the model can hold has its offset
(`Secs`), for comparisons, and its whole days (`Days`), for `days_since`; a time that is not a
whole number of days from the clock gives `days_since` an error value, failing closed.

Left out of the model, and named in `Export.left_out`: actions whose object has no matrix, a
link path to a field some action changes or through a second link, `new.` on a non-creating action, an unknown function, a non-integer number, or a param of a type the model
cannot enumerate, and an action no actor of the model may take.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..decl.models import ActorRule, ByRole, Deny, Domain, Target
from ..expr import parse
from ..expr.ast import Arith, Call, Compare, ListLit, Literal, Logical, Neg, Not, Path
from ..harness.world import world_actors

KERNEL = "external:kernel"
INTS = (0, 1, 2, 7, 30, 100, 1000, 10000)
STRS = ("x", "example", "")
DATES = ("2026-01-01T00:00:00+00:00", "2025-11-02T00:00:00+00:00")   # the clock, and 60 days before
BOUND = 1_000_000

PRELUDE = r"""
N == <<"n">>
E == <<"e">>
S(x) == <<"s", x>>
I(x) == <<"i", x>>
B(x) == <<"b", x>>
L(x) == <<"l", x>>
R(x) == <<"r", x>>
Tag(v) == v[1]
Get(r, f) == IF f \in DOMAIN r THEN r[f] ELSE N
Attr(v, f) == IF Tag(v) = "e" THEN E ELSE IF Tag(v) = "r" THEN Get(v[2], f) ELSE N
Num(v) == IF Tag(v) = "b" THEN (IF v[2] THEN 1 ELSE 0) ELSE v[2]
Eq(a, b) == IF Tag(a) = Tag(b) THEN a = b
            ELSE IF {Tag(a), Tag(b)} = {"b", "i"} THEN Num(a) = Num(b) ELSE FALSE
T(x) == <<"t", x>>
IsTime(v) == Tag(v) = "t" \/ (Tag(v) = "s" /\ v[2] \in DOMAIN Secs)
Sec(v) == IF Tag(v) = "t" THEN v[2] ELSE Secs[v[2]]
OneTime(a, b) == (Tag(a) = "t") # (Tag(b) = "t")
TimeEq(a, b) == IF Tag(a) = "s" \/ Tag(b) = "s" THEN (IF IsTime(a) /\ IsTime(b) THEN B(Sec(a) = Sec(b)) ELSE E)
                ELSE B(FALSE)
OpEq(a, b) == IF Tag(a) = "e" \/ Tag(b) = "e" THEN E ELSE IF OneTime(a, b) THEN TimeEq(a, b) ELSE B(Eq(a, b))
OpNe(a, b) == IF Tag(a) = "e" \/ Tag(b) = "e" THEN E ELSE IF OneTime(a, b) THEN (LET r == TimeEq(a, b) IN IF Tag(r) = "b" THEN B(~r[2]) ELSE r)
              ELSE B(~Eq(a, b))
Mem(a, l) == \E k \in 1..Len(l[2]) : Eq(a, l[2][k])
OpIn(a, l) == IF Tag(a) = "e" \/ Tag(l) # "l" THEN E ELSE B(Mem(a, l))
OpNotIn(a, l) == IF Tag(a) = "e" \/ Tag(l) # "l" THEN E ELSE B(~Mem(a, l))
Ord(a, b) == Tag(a) \in {"i", "b"} /\ Tag(b) \in {"i", "b"}
TOrd(a, b) == (Tag(a) = "t" \/ Tag(b) = "t") /\ IsTime(a) /\ IsTime(b)
OpLt(a, b) == IF Ord(a, b) THEN B(Num(a) < Num(b)) ELSE IF TOrd(a, b) THEN B(Sec(a) < Sec(b)) ELSE E
OpLe(a, b) == IF Ord(a, b) THEN B(Num(a) <= Num(b)) ELSE IF TOrd(a, b) THEN B(Sec(a) <= Sec(b)) ELSE E
OpGt(a, b) == IF Ord(a, b) THEN B(Num(a) > Num(b)) ELSE IF TOrd(a, b) THEN B(Sec(a) > Sec(b)) ELSE E
OpGe(a, b) == IF Ord(a, b) THEN B(Num(a) >= Num(b)) ELSE IF TOrd(a, b) THEN B(Sec(a) >= Sec(b)) ELSE E
DaysSince(v) == IF Tag(v) = "n" THEN N ELSE IF Tag(v) = "t" THEN I(0)
                ELSE IF Tag(v) = "s" /\ v[2] \in DOMAIN Days THEN I(Days[v[2]]) ELSE E
Store(v) == IF Tag(v) = "t" THEN S(NowIso) ELSE v
IsInt(v) == Tag(v) = "i"
OpAdd(a, b) == IF Tag(a) = "s" /\ Tag(b) \in {"s", "i"} THEN S(a[2] \o (IF Tag(b) = "i" THEN ToString(b[2]) ELSE b[2]))
               ELSE IF Tag(b) = "s" /\ Tag(a) = "i" THEN S(ToString(a[2]) \o b[2])
               ELSE IF IsInt(a) /\ IsInt(b) THEN I(a[2] + b[2]) ELSE E
OpSub(a, b) == IF IsInt(a) /\ IsInt(b) THEN I(a[2] - b[2]) ELSE E
OpNeg(a) == IF IsInt(a) THEN I(-a[2]) ELSE E
OpNot(a) == IF Tag(a) = "b" THEN B(~a[2]) ELSE E
OpAnd(a, b) == IF Tag(a) # "b" THEN E ELSE IF ~a[2] THEN B(FALSE) ELSE IF Tag(b) # "b" THEN E ELSE b
OpOr(a, b) == IF Tag(a) # "b" THEN E ELSE IF a[2] THEN B(TRUE) ELSE IF Tag(b) # "b" THEN E ELSE b
OpExists(a) == IF Tag(a) = "e" THEN E ELSE B(Tag(a) # "n")
LinkTo(F, x) == IF Tag(x) = "s" /\ x[2] \in DOMAIN F THEN R(F[x[2]]) ELSE N
Kept(x) == Tag(x) # "n"
LinkOne(F, v) == IF Tag(v) = "e" THEN E ELSE LinkTo(F, v)
LinkMany(F, v) == IF Tag(v) = "l" THEN L(SelectSeq([k \in 1..Len(v[2]) |-> LinkTo(F, v[2][k])], Kept))
                  ELSE IF Tag(v) = "n" THEN N ELSE E
OpCount(a) == IF Tag(a) = "n" THEN I(0) ELSE IF Tag(a) \in {"l", "s"} THEN I(Len(a[2]))
              ELSE IF Tag(a) = "r" THEN I(Cardinality(DOMAIN a[2])) ELSE E
Pass(v) == v = B(TRUE)
"""


class Unsupported(Exception):
    """A construct the model does not cover yet; the action using it is left out."""


@dataclass
class Export:
    module: str                       # the TLA+ module text
    cfg: str                          # the TLC configuration
    name: str                         # the module name
    left_out: dict[str, str] = field(default_factory=dict)    # action → why it is not modeled
    actors: dict[str, str] = field(default_factory=dict)      # role → the actor's id
    steps: list[str] = field(default_factory=list)            # the modeled TLA+ step operators


# -- values ------------------------------------------------------------------------------------
_SAFE = re.compile(r"[A-Za-z0-9 _.:@<>/+\-=,;()\[\]{}!?#$%&*|~^']*")


def tla_str(s: str) -> str:
    """A TLA+ string literal. Text TLC may not read (quotes, backslashes, non-ASCII) becomes
    `u:` and its UTF-8 bytes in hex, which keeps equality, the only thing strings are used for."""
    if _SAFE.fullmatch(s):
        return f'"{s}"'
    return '"u:' + s.encode().hex() + '"'


def value(v: Any) -> str:
    """A Python value as a tagged TLA+ value."""
    if v is None:
        return "N"
    if isinstance(v, bool):
        return f"B({'TRUE' if v else 'FALSE'})"
    if isinstance(v, int):
        return f"I({v})"
    if isinstance(v, float):
        if v.is_integer():
            return f"I({int(v)})"
        raise Unsupported(f"the non-integer number {v}")
    if isinstance(v, str):
        return f"S({tla_str(v)})"
    if isinstance(v, (list, tuple)):
        return "L(<<" + ", ".join(value(x) for x in v) + ">>)"
    if isinstance(v, dict):
        return "R(" + record({k: value(x) for k, x in v.items()}) + ")"
    raise Unsupported(f"the value {v!r}")


def record(fields: dict[str, str]) -> str:
    """A function from field name to (already rendered) value."""
    if not fields:
        return "[f \\in {} |-> N]"
    return "(" + " @@ ".join(f"({tla_str(k)} :> {v})" for k, v in sorted(fields.items())) + ")"


def ident(*parts: str) -> str:
    return "_".join(re.sub(r"[^A-Za-z0-9]", "_", p) for p in parts)


# -- expressions -------------------------------------------------------------------------------
class Expr:
    """Translate a check expression for one action (or invariant) on one object type."""

    def __init__(self, d: Domain, obj: str, actor: str, params: dict[str, str]):
        self.d, self.obj, self.actor, self.params = d, obj, actor, params
        self.links = {n for n, l in d.links.items() if l.from_ == obj}

    def __call__(self, src: str) -> str:
        return self.node(parse(src))

    def node(self, n: Any) -> str:
        match n:
            case Literal(v):
                return value(v)
            case ListLit(items):
                return "L(<<" + ", ".join(self.node(i) for i in items) + ">>)"
            case Path(root, attrs):
                return self.path(root, attrs)
            case Not(x):
                return f"OpNot({self.node(x)})"
            case Neg(x):
                return f"OpNeg({self.node(x)})"
            case Logical(op, a, b):
                return f"Op{'And' if op == 'and' else 'Or'}({self.node(a)}, {self.node(b)})"
            case Arith(op, a, b):
                return f"Op{'Add' if op == '+' else 'Sub'}({self.node(a)}, {self.node(b)})"
            case Compare(op, a, b):
                name = {"==": "Eq", "!=": "Ne", "<": "Lt", "<=": "Le", ">": "Gt", ">=": "Ge",
                        "in": "In", "not_in": "NotIn"}[op]
                return f"Op{name}({self.node(a)}, {self.node(b)})"
            case Call(name, args) if name in ("exists", "count") and len(args) == 1:
                return f"Op{name.capitalize()}({self.node(args[0])})"
            case Call("now", []):
                return "T(0)"                                # the harness's clock, frozen
            case Call("days_since", [x]):
                return f"DaysSince({self.node(x)})"
            case Call(name, _):
                raise Unsupported(f"the function {name}()")
        raise Unsupported(f"the expression {n!r}")

    def path(self, root: str, attrs: tuple[str, ...]) -> str:
        if root == "target":
            if not attrs:
                raise Unsupported("the whole target")
            if attrs[0] in self.links:
                return self.link(attrs)
            base = "R(o)"
        elif root == "actor":
            base = self.actor
        elif root == "params":
            if not attrs:
                raise Unsupported("the whole params")
            if attrs[0] not in self.params:
                base, attrs = "N", ()                     # an undeclared or optional param is null
            else:
                base, attrs = self.params[attrs[0]], attrs[1:]
        else:
            raise Unsupported(f"the root {root}")
        out = base
        for a in attrs:
            out = f"Attr({out}, {tla_str(a)})"
        return out


    def link(self, attrs: tuple[str, ...]) -> str:
        """`target.<link>[.<field>]`: the linked objects are fixtures, read from the constant
        `Fix_<type>`. Sound only for what no modeled action changes, so a field read through the
        link must be one no action sets (the instances stay independent, ADR-0043)."""
        lk = self.d.links[attrs[0]]
        many = lk.cardinality in ("one-to-many", "many-to-many")
        out = f"Link{'Many' if many else 'One'}(Fix_{ident(lk.to)}, Get(o, {tla_str(attrs[0])}))"
        if len(attrs) > 1:
            if many:
                raise Unsupported(f"the link path target.{'.'.join(attrs)} (a field of many)")
            if attrs[1] in changed_fields(self.d).get(lk.to, set()) or \
                    any(l.from_ == lk.to and n == attrs[1] for n, l in self.d.links.items()):
                raise Unsupported(f"the link path target.{'.'.join(attrs)} (a field that changes, or a link)")
            for a in attrs[1:]:
                out = f"Attr({out}, {tla_str(a)})"
        return out


def changed_fields(d: Domain) -> dict[str, set[str]]:
    """Fields some modeled action may change, per object type: `set` effects and the state field
    of a type whose matrix moves. A created object is new, not a change to a fixture."""
    out: dict[str, set[str]] = {}
    for a in d.actions.values():
        if a.creates is not None or a.object_type is None:
            continue
        f = out.setdefault(a.object_type, set())
        for e in a.effects:
            for key in (e.set or {}):
                f.add(key.split(".", 1)[1].split(".")[0] if key.startswith("target.") else key)
        tr = d.transitions.get(a.object_type)
        if tr is not None:
            f.add(tr.field)
    return out


# -- the module --------------------------------------------------------------------------------
def _candidates(d: Domain, spec: Any, actor_ids: list[str]) -> list[Any]:
    if spec.ref is not None:
        return [data["id"] for fx in d.world.fixtures for obj, data in fx.items() if obj == spec.ref]
    if spec.enum:
        return list(spec.enum)
    t = spec.type or "string"
    if t in ("integer", "number"):
        return list(INTS)
    return {"boolean": [True, False], "datetime": list(DATES), "string": list(STRS) + actor_ids}[t]


def model_actors(d: Domain) -> dict[str, Any]:
    """The harness's actors, and the `system` actor a handoff acts as when an action is for it
    (a receiving domain's creating action, such as Delivery's `request_delivery`)."""
    from ..types import Actor
    actors = dict(world_actors(d))
    if any((r.role if isinstance(r, ActorRule) else r) == "system" for a in d.actions.values() for r in a.actor):
        actors["system"] = Actor("handoff:model", "system", ("system",))
    return actors


def export(d: Domain, name: str | None = None, bound: int = BOUND) -> Export:
    mod = name or ident("Toprope", d.domain)
    actors = model_actors(d)
    ids = sorted({a.id for a in actors.values() if a.kind == "person"})
    out = Export(module="", cfg="", name=mod, actors={r: a.id for r, a in actors.items()})

    instances: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for fx in d.world.fixtures:
        for obj, data in fx.items():
            o = d.objects.get(obj)
            if o is None:
                continue
            names = set(o.properties) | {n for n, l in d.links.items() if l.from_ == obj}
            tr = d.transitions.get(obj)
            if tr is not None:
                names.add(tr.field)
            fields = {k: value(data.get(k)) for k in sorted(names)}
            fields["id"] = value(data["id"])
            instances.setdefault(obj, []).append((data["id"], fields))

    # Creation: one fresh id per created type. A creating step runs only from the empty world and
    # makes one object, so a run follows one created object, as a fixture run follows one fixture.
    fresh = {a.creates: f"new-{a.creates}" for a in d.actions.values()
             if a.creates is not None and a.creates in d.objects}
    lines = [f"---- MODULE {mod} ----", "EXTENDS Integers, Sequences, FiniteSets, TLC",
             "VARIABLES obj, last", "vars == <<obj, last>>", *_time_tables(d), PRELUDE]
    modeled = sorted(set(instances) | set(fresh))
    for obj in modeled:
        ids_ = [i for i, _ in instances.get(obj, [])] + ([fresh[obj]] if obj in fresh else [])
        lines.append(f"Ids_{ident(obj)} == {{{', '.join(tla_str(i) for i in ids_)}}}")
    for to in sorted({l.to for l in d.links.values()}):
        fx = instances.get(to, [])
        fix = " @@ ".join(f"({tla_str(i)} :> {record(f)})" for i, f in fx) if fx else "[x \\in {} |-> N]"
        lines.append(f"Fix_{ident(to)} == {fix}")
    for role, a in sorted(actors.items()):
        env = {"id": value(a.id), "kind": value(a.kind), "roles": value(list(a.roles)),
               "role": value(a.roles[0] if a.roles else None)}
        env["principal"] = value({"id": a.id, "kind": a.kind, "roles": list(a.roles), "role": a.roles[0]})
        lines.append(f"Actor_{ident(role)} == R({record(env)})")

    # One fixture per run of the model: no step or invariant reads another instance (link paths
    # are left out, a `ref` param is only an id), so the instances are independent, and checking
    # each alone reaches the same states as checking them together, in a sum, not a product.
    starts = [f"({tla_str(i)} :> {record(f)})" for insts in instances.values() for i, f in insts]
    if fresh or not starts:
        starts.append("[x \\in {} |-> N]")                      # the empty world, where creation starts
    init = "\n          \\/ ".join(f"obj = {x}" for x in starts)
    lines.append(f"Init == /\\ \\/ {init}\n        /\\ last = <<\"init\">>")

    for name_, a in d.actions.items():
        obj = a.object_type
        tr = d.transitions.get(obj)
        if a.creates is not None:
            if a.creates not in d.objects:
                out.left_out[name_] = f"it creates an unknown {a.creates}"
                continue
            try:
                steps = _create(d, name_, a, actors, ids, fresh[a.creates])
            except Unsupported as e:
                out.left_out[name_] = f"it uses {e}"
                continue
            if not steps:
                out.left_out[name_] = "no actor of the model may take it"
                continue
            lines += [s for _, s in steps]
            out.steps += [op for op, _ in steps]
            continue
        if tr is None:
            out.left_out[name_] = f"{obj} has no matrix"
            continue
        if obj not in instances and obj not in fresh:
            out.left_out[name_] = f"no fixture of {obj}, and nothing creates one"
            continue
        try:
            steps = _action(d, name_, a, tr, actors, ids)
        except Unsupported as e:
            out.left_out[name_] = f"it uses {e}"
            continue
        if not steps:
            out.left_out[name_] = "no actor of the model may take it, or no cell allows it"
            continue
        lines += [s for _, s in steps]
        out.steps += [op for op, _ in steps]

    invs = []
    for inv in d.invariants:
        if inv.scope != "aggregate" or inv.on not in modeled:
            continue
        try:
            body = Expr(d, inv.on, "N", {})(inv.check)
        except Unsupported as e:
            out.left_out[f"invariant {inv.id}"] = f"it uses {e}"
            continue
        op = ident("Inv", inv.id)
        lines.append(f"{op} == \\A i \\in Ids_{ident(inv.on)} \\cap DOMAIN obj : LET o == obj[i] IN Pass({body})")
        invs.append(op)

    nxt = " \\/ ".join(out.steps) if out.steps else "FALSE"
    lines += [f"Next == {nxt}", "Spec == Init /\\ [][Next]_vars",
              f"Bound == TLCGet(\"distinct\") < {bound}", "===="]
    out.module = "\n".join(lines) + "\n"
    out.cfg = "\n".join(["INIT Init", "NEXT Next", "CONSTRAINT Bound", "CHECK_DEADLOCK FALSE",
                         *[f"INVARIANT {i}" for i in invs]]) + "\n"
    return out


def _action(d: Domain, name: str, a: Any, tr: Any, actors: dict[str, Any], ids: list[str]) -> list[tuple[str, str]]:
    """One step operator per actor that some rule of the action may admit."""
    obj = a.object_type
    required = {p: s for p, s in a.params.items() if not s.optional}
    pvars = {p: f"p_{ident(p)}" for p in required}
    cands = {}
    for p, s in required.items():
        vals = _candidates(d, s, ids)
        if not vals:
            raise Unsupported(f"the param {p} with no candidate value")
        cands[p] = [[v] if s.many else v for v in vals]
    out = []
    for role, actor in sorted(actors.items()):
        if a.requires == "human" and actor.kind != "person":
            continue
        rules = [r for r in a.actor if (r.role if isinstance(r, ActorRule) else r) in actor.roles]
        if not rules:
            continue
        ex = Expr(d, obj, f"Actor_{ident(role)}", {p: v for p, v in pvars.items()})
        if any(isinstance(r, str) or not r.where for r in rules):
            who = "TRUE"
        else:
            who = " \\/ ".join(f"Pass({ex(r.where)})" for r in rules)
        moves = []
        from ..decl.rules import covering, meets
        for state, cells in tr.matrix.items():
            to = _resolve(cells.get(name, "undecided"), actor.roles)
            if to is not None and all(meets(r, actor.kind, actor.roles) for _, r in covering(d, name, state)):
                moves.append(f"<<{tla_str(state)}, {tla_str(to)}>>")   # an outcome rule removes the move (ADR-0048)
        if not moves:
            continue
        pre = [f"Pass({ex(p.check)})" for p in a.preconditions]
        sets = {}
        for e in a.effects:
            for key, v in (e.set or {}).items():
                if key.startswith("new."):
                    raise Unsupported("new.")
                attr = key.split(".", 1)[1] if key.startswith("target.") else key
                sets[attr] = f"Store({ex(v)})" if isinstance(v, str) else value(v)
        op = ident("Step", name, role)
        args = ", ".join(f"{pvars[p]} \\in {{{', '.join(value(v) for v in cands[p])}}}" for p in required)
        params_rec = "<<" + ", ".join(f"<<{tla_str(p)}, {pvars[p]}>>" for p in required) + ">>"
        sf = tla_str(tr.field)
        guard = [f"Get(o, {sf}) = S(mv[1])", who, *pre, *[f"Tag({v}) # \"e\"" for v in sets.values()]]
        body = (f"{op} == \\E i \\in Ids_{ident(obj)} \\cap DOMAIN obj :" +
                (f" \\E {args} :" if args else "") +
                f" \\E mv \\in {{{', '.join(moves)}}} :\n    LET o == obj[i] IN\n    /\\ " +
                "\n    /\\ ".join(guard) +
                f"\n    /\\ obj' = [obj EXCEPT ![i] = {_set_fields(sf, sets)}]" +
                f"\n    /\\ last' = <<{tla_str(name)}, {tla_str(role)}, i, {params_rec}>>")
        out.append((op, body))
    return out


def _create(d: Domain, name: str, a: Any, actors: dict[str, Any], ids: list[str], new_id: str) -> list[tuple[str, str]]:
    """One step operator per actor that may take a creating action: from the empty world only,
    it makes `new_id` with every field of its type (null unless given), the declared params that
    name a field, the initial state, then each `set` effect (`new.` and `target.` alike)."""
    obj = a.creates
    tr = d.transitions.get(obj)
    names = set(d.objects[obj].properties) | {n for n, l in d.links.items() if l.from_ == obj}
    if tr is not None:
        names.add(tr.field)
    required = {p: s for p, s in a.params.items() if not s.optional}
    pvars = {p: f"p_{ident(p)}" for p in required}
    read = _reads(d, obj, a)
    cands = {}
    for p, s in required.items():
        vals = _candidates(d, s, ids)
        if not vals:
            raise Unsupported(f"the param {p} with no candidate value")
        if p not in read:          # nothing reads it: one value stands for all (a smaller model)
            vals = vals[:1]
        cands[p] = [[v] if s.many else v for v in vals]
    base = {k: "N" for k in sorted(names)}
    base["id"] = value(new_id)
    for p in required:
        if p in names and (tr is None or p != tr.field):
            base[p] = pvars[p]
    if tr is not None and tr.initial:
        base[tr.field] = value(tr.initial)
    out = []
    from ..decl.rules import covering, meets
    for role, actor in sorted(actors.items()):
        if a.requires == "human" and actor.kind != "person":
            continue
        if not all(meets(r, actor.kind, actor.roles) for _, r in covering(d, name, None)):
            continue
        rules = [r for r in a.actor if (r.role if isinstance(r, ActorRule) else r) in actor.roles]
        if not rules:
            continue
        ex = Expr(d, obj, f"Actor_{ident(role)}", dict(pvars))
        who = "TRUE" if any(isinstance(r, str) or not r.where for r in rules) else \
            " \\/ ".join(f"Pass({ex(r.where)})" for r in rules)
        pre = [f"Pass({ex(p.check)})" for p in a.preconditions]
        sets = {}
        for e in a.effects:
            for key, v in (e.set or {}).items():
                attr = key.split(".", 1)[1] if key.startswith(("target.", "new.")) else key
                sets[attr] = f"Store({ex(v)})" if isinstance(v, str) else value(v)
        new = record(base)
        for attr, v in sorted(sets.items()):
            new = f"({tla_str(attr)} :> {v}) @@ ({new})"
        op = ident("Create", name, role)
        args = ", ".join(f"{pvars[p]} \\in {{{', '.join(value(v) for v in cands[p])}}}" for p in required)
        params_rec = "<<" + ", ".join(f"<<{tla_str(p)}, {pvars[p]}>>" for p in required) + ">>"
        guard = ["DOMAIN obj = {}", who, *pre, *[f"Tag({v}) # \"e\"" for v in sets.values()]]
        body = (f"{op} ==" + (f" \\E {args} :" if args else "") +
                "\n    LET o == [x \\in {} |-> N] IN\n    /\\ " + "\n    /\\ ".join(guard) +
                f"\n    /\\ obj' = ({tla_str(new_id)} :> {new})" +
                f"\n    /\\ last' = <<{tla_str(name)}, {tla_str(role)}, {tla_str(new_id)}, {params_rec}>>")
        out.append((op, body))
    return out


def _reads(d: Domain, obj: str, creating: Any) -> set[str]:
    """Field and param names an expression may read on objects of `obj`: in the creating
    action, in any action on `obj`, and in `obj`'s invariants. A param no expression reads
    cannot change any step or check, so creation tries one value for it."""
    texts = [p.check for p in creating.preconditions]
    texts += [r.where for r in creating.actor if isinstance(r, ActorRule) and r.where]
    texts += [v for e in creating.effects for v in (e.set or {}).values() if isinstance(v, str)]
    for a in d.actions.values():
        if a.object_type != obj:
            continue
        texts += [p.check for p in a.preconditions]
        texts += [r.where for r in a.actor if isinstance(r, ActorRule) and r.where]
        texts += [v for e in a.effects for v in (e.set or {}).values() if isinstance(v, str)]
    texts += [i.check for i in d.invariants if i.on == obj]
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", " ".join(texts)))
    return {p for p in creating.params if p in words}


def _time_tables(d: Domain) -> list[str]:
    """Time, frozen at the harness's clock (replay uses the same one). Every ISO time the model
    can hold (the fixtures' values, the datetime candidates, the clock's own) gets its offset in
    seconds from the clock (`Secs`), and, when it is a whole number of days, `days_since` of it
    (`Days`): the interpreter's `days_since` is fractional, so a time that is not whole days
    from the clock fails closed (`E`) and is named as such."""
    from datetime import datetime, timezone

    from ..harness.run import NOW
    now_iso = NOW.isoformat()

    def walk(v: Any):
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from walk(x)
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)
    found: dict[str, int] = {}
    for s_ in [now_iso, *DATES, *(x for fx in d.world.fixtures for data in fx.values() for x in walk(data))]:
        try:
            t = datetime.fromisoformat(s_)
        except ValueError:
            continue
        t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        found[s_] = int((t - NOW).total_seconds())
    secs = " @@ ".join(f"({tla_str(k)} :> {v})" for k, v in sorted(found.items())) or "[x \\in {} |-> 0]"
    whole = {k: -v // 86400 for k, v in found.items() if v % 86400 == 0}
    days = " @@ ".join(f"({tla_str(k)} :> {v})" for k, v in sorted(whole.items())) or "[x \\in {} |-> 0]"
    return [f"NowIso == {tla_str(now_iso)}", f"Secs == {secs}", f"Days == {days}"]


def _set_fields(sf: str, sets: dict[str, str]) -> str:
    """The new instance: the state field moved, then each `set` effect, on fields present or
    added (a function's domain grows with `@@`)."""
    new = f"({sf} :> S(mv[2])) @@ o"
    for attr, v in sorted(sets.items()):
        new = f"({tla_str(attr)} :> {v}) @@ ({new})"
    return new


def _resolve(c: Any, roles: tuple[str, ...]) -> str | None:
    """The target state a cell allows an actor with these roles, or None."""
    if isinstance(c, Target):
        return c.to
    if isinstance(c, Deny) or c in ("n/a", "undecided"):
        return None
    if isinstance(c, ByRole):
        listed = [c.by_role[r] for r in roles if r in c.by_role]
        if not listed or any(isinstance(x, Deny) or x in ("n/a", "undecided") for x in listed):
            return None
        tos = {x.to if isinstance(x, Target) else x for x in listed}
        return tos.pop() if len(tos) == 1 else None
    return c


def write(e: Export, out_dir: Any) -> None:
    from pathlib import Path as P
    d = P(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{e.name}.tla").write_text(e.module)
    (d / f"{e.name}.cfg").write_text(e.cfg)
    (d / f"{e.name}.left-out.json").write_text(json.dumps(e.left_out, indent=2, sort_keys=True) + "\n")


__all__ = ["BOUND", "Export", "Unsupported", "export", "value", "write"]
