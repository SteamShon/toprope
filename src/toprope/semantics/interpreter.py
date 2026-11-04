"""The model interpreter: the oracle for every generated surface (docs/semantics.md §2).

`decide()` is pure. Given the current projected state and a command, it returns what should
happen: an outcome and the events to append. It never touches a store. Steps 1-3 (identity,
idempotency, load) and step 11 (append with retry) belong to the caller (`ReferenceModel`,
later `Execution`). Approvals (step 7) and reservations (step 8) arrive with ADR-0015 in M0b.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..decl.models import Action, ActorRule, ByRole, Deny, Domain, Target
from ..expr import Env, EvalError, parse, evaluate
from .types import Actor, Command, Event, Outcome

Lookup = Callable[[str], "dict[str, Any] | None"]


class ObjectView(Mapping):
    """An object's state where link fields resolve to the linked objects' state."""

    def __init__(self, domain: Domain, obj_type: str, state: Mapping[str, Any], lookup: Lookup):
        self._d, self._t, self._s, self._lookup = domain, obj_type, state, lookup

    def _link(self, name: str):
        link = self._d.links.get(name)
        return link if link is not None and link.from_ == self._t else None

    def __getitem__(self, key: str) -> Any:
        if key not in self._s:
            raise KeyError(key)
        v = self._s[key]
        link = self._link(key)
        if link is None or v is None:
            return v
        if isinstance(v, list):
            return [self._view(link.to, i) for i in v]
        return self._view(link.to, v)

    def _view(self, obj_type: str, oid: str) -> Any:
        st = self._lookup(oid)
        return None if st is None else ObjectView(self._d, obj_type, st, self._lookup)

    def __iter__(self):
        return iter(self._s)

    def __len__(self) -> int:
        return len(self._s)


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    events: tuple[Event, ...]      # domain + decision events to append at the loaded version
    attempts: tuple[Event, ...]    # DeniedAttempt / InvariantGuardTriggered (attempts stream)


def _pascal(name: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in name.split("_"))


class Interpreter:
    def __init__(self, domain: Domain, clock: Callable[[], datetime] | None = None):
        self.d = domain
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._parsed: dict[str, Any] = {}

    # -- helpers -------------------------------------------------------------------------
    def _expr(self, src: str):
        if src not in self._parsed:
            self._parsed[src] = parse(src)
        return self._parsed[src]

    def _env(self, target: Any, actor: Actor | None, params: dict[str, Any], new: Any = None) -> Env:
        return Env({"target": target, "actor": actor.as_env() if actor else None,
                    "params": params, "new": new}, clock=self.clock)

    def _rule_ok(self, rule: str | ActorRule, actor: Actor, view: Any, params: dict) -> bool:
        role = rule.role if isinstance(rule, ActorRule) else rule
        if role not in actor.roles:
            return False
        if isinstance(rule, ActorRule) and rule.where:
            try:
                return evaluate(self._expr(rule.where), self._env(view, actor, params)) is True
            except EvalError:
                return False
        return True

    def actor_allowed(self, action: Action, cmd: Command, view: Any) -> tuple[bool, str]:
        """Step 4: role or relation, grant, `requires: human`. Agents need both their own rule
        and their principal's rule to pass, plus a grant covering the action (ADR-0016)."""
        a = cmd.actor
        assert a is not None
        if action.requires == "human" and a.kind != "person":
            return False, f"Only a person can {cmd.action}."
        if not any(self._rule_ok(r, a, view, cmd.params) for r in action.actor):
            return False, f"{a.id} may not {cmd.action}."
        if a.kind == "agent":
            p, g = cmd.on_behalf_of, cmd.grant
            if p is None or g is None:
                return False, "An agent needs a principal and a grant."
            if cmd.action not in g.actions or (g.targets is not None and cmd.target not in g.targets):
                return False, f"Grant {g.id} does not cover {cmd.action} on {cmd.target}."
            if g.expires_at is not None and (cmd.at or self.clock()) >= g.expires_at:
                return False, f"Grant {g.id} has expired."
            if not any(self._rule_ok(r, p, view, cmd.params) for r in action.actor):
                return False, f"Principal {p.id} may not {cmd.action}."
        return True, ""

    def cell(self, obj_type: str, state: str, action: str, actor: Actor) -> str | Deny:
        """Step 5: resolve the matrix cell for this actor. Missing cell or row → undecided."""
        tr = self.d.transitions[obj_type]
        c = tr.matrix.get(state, {}).get(action, "undecided")
        if isinstance(c, Target):
            return c.to
        if isinstance(c, ByRole):
            for role in actor.roles:
                if role in c.by_role:
                    return c.by_role[role]
            return "n/a"
        return c

    # -- the decision ----------------------------------------------------------------------
    def decide(self, cmd: Command, state: dict[str, Any] | None, lookup: Lookup) -> Decision:
        d, at = self.d, cmd.at or self.clock()
        if cmd.actor is None:
            return Decision(Outcome("rejected", "unauthenticated", "Unknown actor."), (), ())
        action = d.actions.get(cmd.action)
        if action is None:
            return Decision(Outcome("rejected", "unknown-action", f"No action {cmd.action}."), (), ())
        obj = action.object_type
        creating = action.creates is not None
        if creating and state is not None:
            return Decision(Outcome("rejected", "exists", f"{cmd.target} already exists."), (), ())
        if not creating and state is None:
            return Decision(Outcome("rejected", "not-found", f"No {obj} {cmd.target}."), (), ())

        meta = dict(at=at, actor=cmd.actor.ref(), domain_version=d.version,
                    on_behalf_of=cmd.on_behalf_of.ref() if cmd.on_behalf_of else None,
                    grant=cmd.grant.id if cmd.grant else None, thread_id=cmd.thread_id, run_id=cmd.run_id)
        stream = cmd.target or ""

        def deny(code: str, reason: str) -> Decision:
            ev = Event("DeniedAttempt", stream, obj, kind="attempt",
                       payload={"action": cmd.action, "code": code, "reason": reason, "params": cmd.params}, **meta)
            return Decision(Outcome("denied", code, reason, state), (), (ev,))

        current = state or {}
        view = ObjectView(d, obj, current, lookup)

        ok, why = self.actor_allowed(action, cmd, view)                                   # step 4
        if not ok:
            return deny("actor", why)

        tr = d.transitions.get(obj)
        if creating:                                                                        # no source state
            next_state = tr.initial if tr else None
        elif tr is not None:                                                                # step 5
            c = self.cell(obj, current.get(tr.field), cmd.action, cmd.actor)
            if c == "n/a":
                return deny("not-applicable", f"Not applicable when {current.get(tr.field)}.")
            if c == "undecided":
                return deny("undecided", "Undecided.")
            if isinstance(c, Deny):
                return deny("matrix", c.deny)
            next_state = c
        else:
            next_state = None

        for pre in action.preconditions:                                                    # step 6
            try:
                passed = evaluate(self._expr(pre.check), self._env(view, cmd.actor, cmd.params)) is True
            except EvalError as e:
                return deny(pre.id, f"{pre.reason} (could not evaluate: {e})")
            if not passed:
                return deny(pre.id, pre.reason)

        new = copy.deepcopy(current)                                                        # step 9
        changes: dict[str, Any] = {}
        if creating:
            new = {"id": cmd.target, **{k: v for k, v in cmd.params.items() if k in d.objects[obj].properties
                                        or (k in d.links and d.links[k].from_ == obj)}}
            changes.update(new)
        if tr is not None and next_state is not None:
            new[tr.field] = changes[tr.field] = next_state
        for eff in action.effects:
            for key, value in (eff.set or {}).items():
                attr = key.split(".", 1)[1] if key.startswith(("target.", "new.")) else key
                if isinstance(value, str):
                    try:
                        value = evaluate(self._expr(value), self._env(view, cmd.actor, cmd.params))
                    except EvalError as e:
                        return Decision(Outcome("rejected", "effect-error", f"{key}: {e}", state), (), ())
                if isinstance(value, datetime):
                    value = value.isoformat()
                new[attr] = changes[attr] = value

        new_view = ObjectView(d, obj, new, lookup)                                          # step 10
        for inv in d.invariants:
            if inv.on != obj or inv.scope != "aggregate":
                continue
            try:
                holds = evaluate(self._expr(inv.check), self._env(new_view, cmd.actor, cmd.params)) is True
            except EvalError:
                holds = False
            if not holds:
                ev = Event("InvariantGuardTriggered", stream, obj, kind="attempt",
                           payload={"action": cmd.action, "invariant": inv.id, "reason": inv.reason}, **meta)
                return Decision(Outcome("rejected", "invariant-guard", inv.reason, state), (), (ev,))

        etype = action.event or (f"{obj}Created" if creating else f"{obj}{_pascal(cmd.action)}")
        events = [Event(etype, stream, obj, payload={"changes": changes, "params": cmd.params,
                                                     "action": cmd.action}, **meta)]
        if action.records_decision:
            events.append(Event("DecisionRecorded", stream, obj, kind="decision",
                                payload={"action": cmd.action, "params": cmd.params, "inputs": current}, **meta))
        return Decision(Outcome("ok", state=new), tuple(events), ())

    def allowed_actions(self, obj_type: str, state: dict[str, Any], actor: Actor, lookup: Lookup) -> list[str]:
        """Actions this actor could take now (a dry run of steps 4-6, then 9-10). Used by views
        and by `read` steps; it must agree with decide() (parity)."""
        out = []
        for name, a in self.d.actions.items():
            if a.target != obj_type:
                continue
            dec = self.decide(Command(actor, name, state.get("id"), {}), state, lookup)
            if dec.outcome.ok:
                out.append(name)
        return out
