"""Domain composition (ADR-0026): domains never inherit from each other; they connect only
through published interfaces. A `*.composition.yaml` declares a system's members and wiring:

    composition: toprope-self
    version: 1
    members:
      authoring: {declaration: authoring.domain.yaml, interface: 1}
      delivery:  {declaration: delivery.domain.yaml,  interface: 1}
    wiring:
      - {from: authoring.deliver, to: delivery.request_delivery}

A member's key is its declared `domain` name. `from` is `<member>.<handoff>`, `to` is
`<member>.<action>`. Compiling checks every member, that every handoff is wired exactly as it
declares, and each wire's contract against the receiver's published interface major.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, ValidationError

from ..decl import Domain, Issue, check_handoffs, load_yaml, validate_domain
from ..decl.models import Ident, Strict

FORMAT = "toprope.world-map.composed/1"


class Member(Strict):
    declaration: str
    interface: Annotated[int, Field(ge=1)] = 1      # the member's published interface major


class Wire(Strict):
    from_: str = Field(alias="from")                # <member>.<handoff>
    to: str                                         # <member>.<action>


class CompositionSpec(Strict):
    composition: Ident
    version: Annotated[int, Field(ge=1)]
    members: dict[str, Member]
    wiring: list[Wire] = Field(default_factory=list)


@dataclass
class Composition:
    spec: CompositionSpec
    domains: dict[str, Domain]
    root: Path

    @property
    def name(self) -> str:
        return self.spec.composition

    def wires(self) -> list[tuple[str, str, str, str]]:
        """(sender, handoff, receiver, action) for each wire that parses."""
        out = []
        for w in self.spec.wiring:
            s, _, h = w.from_.partition(".")
            r, _, a = w.to.partition(".")
            if s and h and r and a:
                out.append((s, h, r, a))
        return out


def load_composition(path: str | Path) -> Composition:
    p = Path(path)
    spec = CompositionSpec.model_validate(load_yaml(p.read_text()))
    domains = {}
    for name, m in spec.members.items():
        try:
            domains[name] = Domain.model_validate(load_yaml((p.parent / m.declaration).read_text()))
        except (OSError, ValidationError) as e:
            raise ValueError(f"member {name}: {m.declaration}: {e}") from None
    return Composition(spec, domains, p.parent)


def check_composition(c: Composition) -> list[Issue]:
    out: list[Issue] = []
    add = out.append
    seen: dict[str, str] = {}
    for name, d in c.domains.items():
        where = f"members.{name}"
        if d.domain != name:
            add(Issue("member-name", where, f"the key must be the declared domain name '{d.domain}'"))
        if d.domain in seen:
            add(Issue("duplicate-member", where, f"domain '{d.domain}' is already member '{seen[d.domain]}'"))
        seen[d.domain] = name
        for i in validate_domain(d):
            if i.severity == "error":
                add(Issue(i.code, f"{where}.{i.where}", i.message))

    wired: set[tuple[str, str]] = set()
    for k, w in enumerate(c.spec.wiring):
        where = f"wiring[{k}]"
        s, _, h = w.from_.partition(".")
        r, _, a = w.to.partition(".")
        if not (s and h and r and a):
            add(Issue("bad-wire", where, "use from: <member>.<handoff>, to: <member>.<action>"))
            continue
        sender = c.domains.get(s)
        if sender is None or r not in c.domains:
            add(Issue("unknown-member", where, f"no member '{s if sender is None else r}'"))
            continue
        hd = sender.handoffs.get(h)
        if hd is None:
            add(Issue("unknown-handoff", where, f"{s} declares no handoff '{h}'"))
            continue
        if (hd.to.domain, hd.to.action) != (r, a):
            add(Issue("wire-mismatch", where, f"{s}.{h} declares {hd.to.domain}.{hd.to.action}, not {r}.{a}"))
        if (s, h) in wired:
            add(Issue("duplicate-wire", where, f"{s}.{h} is wired twice"))
        wired.add((s, h))

    published = {n: (d, c.spec.members[n].interface) for n, d in c.domains.items()}
    for name, d in c.domains.items():
        for h in d.handoffs:
            if (name, h) not in wired:
                add(Issue("unwired-handoff", f"members.{name}.handoffs.{h}",
                          f"{name}.{h} is declared but not wired in this composition"))
        for i in check_handoffs(d, published):
            add(Issue(i.code, f"members.{name}.{i.where}", i.message))
    return out


def accepts(c: Composition) -> dict[str, dict[str, set[str]]]:
    """For each receiving member: action → the wired handoffs `<sender>.<handoff>`."""
    out: dict[str, dict[str, set[str]]] = {n: {} for n in c.domains}
    for s, h, r, a in c.wires():
        out.setdefault(r, {}).setdefault(a, set()).add(f"{s}.{h}")
    return out


def assemble(c: Composition, stores: dict[str, Any], identity: Any,
             clock: Callable[[], datetime] | None = None, services: Any = None) -> dict[str, Any]:
    """One Execution per member, wired in process: each sends its handoffs through a local
    transport, each receiver accepts only the handoffs wired to it, and kernel-service calls
    run on `services` (ADR-0028)."""
    from ..exec import Execution
    from ..handoff import LocalTransport
    acc = accepts(c)
    exs = {n: Execution(d, stores[n], identity, clock=clock, accepts=acc.get(n, {}), services=services)
           for n, d in c.domains.items()}
    transport = LocalTransport(exs)
    for ex in exs.values():
        ex.transport = transport
    return exs


# -- the composed world map ------------------------------------------------------------------------
def composed_world_map(c: Composition, harness: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    from ..worldmap import build_world_map
    members = {n: build_world_map(d, (harness or {}).get(n)) for n, d in sorted(c.domains.items())}
    wires = []
    for s, h, r, a in c.wires():
        hd = c.domains[s].handoffs.get(h)
        ra = c.domains[r].actions.get(a)
        if hd is None or ra is None:
            continue
        wires.append({"from": {"domain": s, "handoff": h, "action": hd.when.action},
                      "to": {"domain": r, "action": a, "object": ra.object_type, "creates": ra.creates is not None}})
    return {"format": FORMAT, "composition": c.name, "version": c.spec.version, "members": members, "wires": wires}


def _reach(wmap, obj, frm, to, roles):
    from ..worldmap import how_to_reach
    return how_to_reach(wmap, obj, frm, to, roles)


def _states_taking(wmap: dict[str, Any], obj: str, action: str, role: str | None = None) -> list[str]:
    """States of `obj` in which `action` is allowed (for `role`, if given)."""
    from ..worldmap import NEW, _targets
    return [e["from"] for e in wmap["behavior"]["edges"]
            if e["object"] == obj and e["action"] == action and e["from"] != NEW
            and any(role is None or r is None or r == role for r, _ in _targets(e["outcome"]))]


def how_to_reach_across(cmap: dict[str, Any], domain: str, obj: str, from_state: str | None,
                        to_domain: str, to_obj: str, target_state: str,
                        roles: tuple[str, ...] | None = None, _depth: int = 0) -> dict[str, Any]:
    """The shortest path from an object's state in one member to a state of an object in
    another, following wires. Steps carry their `domain`; a handoff step is taken by `system`."""
    from ..worldmap import NEW
    members = cmap["members"]
    if domain == to_domain and obj == to_obj:
        out = _reach(members[domain], obj, from_state, target_state, roles)
        for s in out.get("steps", []):
            s["domain"] = domain
        return out
    if _depth > len(members):
        return {"reachable": False, "reason": "no wiring leads there"}
    best = None
    for w in cmap["wires"]:
        if w["from"]["domain"] != domain:
            continue
        smap = members[domain]
        # 1. In the sender: reach a state where the handing-off action is allowed, then take it.
        for st in _states_taking(smap, obj, w["from"]["action"]):
            pre = (_reach(smap, obj, from_state, st, roles) if st != (from_state or NEW)
                   else {"reachable": True, "steps": []})
            take = _step(smap, obj, st, w["from"]["action"], roles)
            if not pre.get("reachable") or take is None:
                continue
            sender_steps = [dict(x, domain=domain) for x in pre["steps"]] + [dict(take, domain=domain)]
            # 2. In the receiver: the wired action, taken by system, then onward.
            r, ra, robj = w["to"]["domain"], w["to"]["action"], w["to"]["object"]
            rmap = members[r]
            starts = [NEW] if w["to"]["creates"] else _states_taking(rmap, robj, ra, role="system")
            for rs in starts:
                after = _after(rmap, robj, rs, ra, role="system")   # a handoff is taken by system
                if not after:
                    continue
                landed = sorted(after)[0]                          # one outcome per role: at most one
                hand = {"domain": r, "action": ra, "from": rs, "to": landed,
                        "who": [f"system (handoff {domain}.{w['from']['handoff']})"], "requires": [],
                        "requires_human": False, **({"you_can": False} if roles is not None else {})}
                if not w["to"]["creates"]:
                    hand["assumes"] = f"the {robj} is {rs}"
                rest = how_to_reach_across(cmap, r, robj, landed, to_domain, to_obj, target_state, roles, _depth + 1)
                if not rest.get("reachable"):
                    continue
                steps = sender_steps + [hand] + rest["steps"]
                if best is None or len(steps) < len(best):
                    best = steps
    if best is None:
        return {"reachable": False, "reason": f"No declared path from {domain}.{obj} to {to_domain}.{to_obj} {target_state}."}
    return {"reachable": True, "steps": best}


def _step(wmap: dict[str, Any], obj: str, state: str, action: str,
          roles: tuple[str, ...] | None) -> dict[str, Any] | None:
    """The step that takes `action` from `state`, in how_to_reach's shape."""
    from ..worldmap import _targets
    for e in wmap["behavior"]["edges"]:
        if e["object"] != obj or e["from"] != state or e["action"] != action:
            continue
        allowed = {a["role"] for a in e["unlock"]["actors"]}
        for role, to in _targets(e["outcome"]):
            who = sorted(allowed if role is None else allowed & {role})
            if who:
                out = {"action": action, "from": state, "to": to, "who": who,
                       "requires": [p["reason"] for p in e["unlock"]["preconditions"]],
                       "requires_human": e["unlock"]["requires_human"]}
                if roles is not None:
                    out["you_can"] = bool(set(roles) & set(who))
                return out
    return None


def _after(wmap: dict[str, Any], obj: str, state: str, action: str, role: str | None = None) -> set[str]:
    """Where `action` leads from `state`: for `role` if given (its by_role entry, or a plain cell)."""
    from ..worldmap import _targets
    return {to for e in wmap["behavior"]["edges"]
            if e["object"] == obj and e["from"] == state and e["action"] == action
            for r, to in _targets(e["outcome"]) if role is None or r is None or r == role}


__all__ = ["FORMAT", "Composition", "CompositionSpec", "accepts", "assemble", "check_composition",
           "composed_world_map", "how_to_reach_across", "load_composition"]
