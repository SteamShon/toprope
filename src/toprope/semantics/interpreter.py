"""The model interpreter: the oracle for every generated surface (docs/semantics.md §2).

`decide()` is pure. Given the current projected state and a command, it returns what should
happen: an outcome and the events to append. It never touches a store. Steps 1-3 (identity,
idempotency, load) and step 11 (append with retry) belong to the caller (`ReferenceModel`,
later `Execution`). Approvals (step 7) and reservations (step 8) arrive with ADR-0015 in M0b.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..decl.models import Action, ActorRule, ByRole, Deny, Domain, Invariant, Target
from ..expr import Env, EvalError, evaluate, parse, paths_read
from ..kernel import CATALOG
from .types import Actor, Command, Event, Grant, Outcome

# lookup(oid) -> (object type, state) or None
Lookup = Callable[[str], "tuple[str, dict[str, Any]] | None"]


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
            # Dangling or wrong-type ids are dropped, so count() never counts them (fail closed).
            return [x for x in (self._view(link.to, i) for i in v) if x is not None]
        return self._view(link.to, v)

    def _view(self, obj_type: str, oid: str) -> Any:
        found = self._lookup(oid)
        if found is None or found[0] != obj_type:
            return None
        return ObjectView(self._d, obj_type, found[1], self._lookup)

    def __iter__(self):
        return iter(self._s)

    def __len__(self) -> int:
        return len(self._s)


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    events: tuple[Event, ...]      # domain + decision events to append at the loaded version
    attempts: tuple[Event, ...]    # DeniedAttempt / InvariantGuardTriggered (attempts stream)


def _unstorable(v: Any) -> str | None:
    """Walk a value like the store codec does; say why it cannot be stored, if it cannot."""
    if isinstance(v, float) and not math.isfinite(v):
        return "must contain only finite numbers"
    if isinstance(v, str) and "\x00" in v:
        return "must not contain NUL characters"
    if isinstance(v, dict):
        return next((w for k, x in v.items() for w in (_unstorable(k), _unstorable(x)) if w), None)
    if isinstance(v, (list, tuple)):
        return next((w for x in v if (w := _unstorable(x))), None)
    return None


def _pascal(name: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in name.split("_"))


RESERVED_ID_PREFIXES = ("handoff:", "effect:")   # the outbox's resolution streams (ADR-0024, ADR-0028)


def _of_type(v: Any, t: str) -> bool:
    if t == "boolean":
        return isinstance(v, bool)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "strings":
        return isinstance(v, list) and all(isinstance(x, str) for x in v)
    return isinstance(v, str)


def origin_person(cmd: Command) -> dict[str, Any] | None:
    """The person a handoff acts on behalf of: the caller if a person, an agent's principal,
    or whoever a system actor itself acted for (docs/domain-schema.md, Handoffs)."""
    a = cmd.actor
    if a is not None and a.kind == "person":
        return a.ref()
    return cmd.on_behalf_of.ref() if cmd.on_behalf_of is not None else None


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

    def _env(self, target: Any, actor: Actor | None, params: dict[str, Any], new: Any = None,
             principal: Actor | None = None) -> Env:
        """`actor.principal` is whom the actor answers for (ADR-0041, Resolved 4): an agent's
        principal, or the actor itself, so a rule can say "not the proposer, nor their agent"."""
        env = None
        if actor is not None:
            env = actor.as_env()
            who = principal if principal is not None and actor.kind == "agent" else actor
            env["principal"] = {k: v for k, v in who.as_env().items() if k in ("id", "kind", "roles", "role")}
        return Env({"target": target, "actor": env, "params": params, "new": new}, clock=self.clock)

    @staticmethod
    def _permissions(cmd: Command) -> dict[str, Any] | None:
        """The permissions in force when the command ran: the actor's roles, the principal's,
        and the grant's scope. Toprope does not issue them (the Identity port does, ADR-0016), so
        it records them with what they allowed; a changed role or a new grant shows as a
        difference between events (ADR-0041, Resolved 5)."""
        if cmd.actor is None:
            return None
        out: dict[str, Any] = {"roles": list(cmd.actor.roles)}
        if cmd.on_behalf_of is not None:
            out["principal_roles"] = list(cmd.on_behalf_of.roles)
        if cmd.grant is not None:
            g = cmd.grant
            out["grant"] = {"id": g.id, "actions": sorted(g.actions),
                            "targets": sorted(g.targets) if g.targets is not None else None,
                            "expires_at": g.expires_at.isoformat() if g.expires_at else None}
        return out

    @staticmethod
    def _principal(cmd: Command) -> Actor | None:
        return cmd.on_behalf_of if cmd.actor.kind == "agent" else None

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
        and their principal's rule to pass, plus a grant covering the action (ADR-0016).
        The principal must be a person (ADR-0021)."""
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
            if p.kind != "person":
                return False, "An agent acts only on behalf of a person."
            if cmd.action not in g.actions or (g.targets is not None and cmd.target not in g.targets):
                return False, f"Grant {g.id} does not cover {cmd.action} on {cmd.target}."
            if g.expires_at is not None and (cmd.at or self.clock()) >= g.expires_at:
                return False, f"Grant {g.id} has expired."
            if not any(self._rule_ok(r, p, view, cmd.params) for r in action.actor):
                return False, f"Principal {p.id} may not {cmd.action}."
        return True, ""

    def cell(self, obj_type: str, state: str, action: str, actors: list[Actor]) -> str | Deny:
        """Step 5: resolve the matrix cell. Missing cell or row → undecided.

        A `by_role` cell is resolved for every given actor (an agent and its principal) and every
        role each holds that the cell lists (roles it does not list are n/a). The cell allows
        only if all of them allow the same target state; otherwise the most restrictive outcome
        wins: deny, then n/a, then undecided (ADR-0021). The result never depends on role order.
        """
        tr = self.d.transitions[obj_type]
        c = tr.matrix.get(state, {}).get(action, "undecided")
        if isinstance(c, Target):
            return c.to
        if not isinstance(c, ByRole):
            return c
        outcomes: list[str | Deny] = []
        for actor in actors:
            listed = [r for r in actor.roles if r in c.by_role]
            outcomes += [c.by_role[r] for r in listed] or ["n/a"]
        denies = [o for o in outcomes if isinstance(o, Deny)]
        if denies:
            return denies[0]
        for special in ("n/a", "undecided"):
            if special in outcomes:
                return special
        targets = set(outcomes)
        return targets.pop() if len(targets) == 1 else Deny(deny="Roles disagree on this transition.")

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
        bad = self.invalid_params(action, cmd.params)                       # ADR-0021: input check
        if cmd.target is not None and cmd.target.startswith(RESERVED_ID_PREFIXES):
            bad = f"Object ids may not start with {' or '.join(RESERVED_ID_PREFIXES)} (outbox records)."
        if cmd.target is None or bad:
            why = "A target id is required." if cmd.target is None else bad
            return Decision(Outcome("rejected", "invalid-command", why), (), ())
        if (creating and state is not None) or (not creating and state is None):
            # Existence is only revealed to actors whose role could act at all (ADR-0021).
            roles = {r.role if isinstance(r, ActorRule) else r for r in action.actor}
            principal = cmd.on_behalf_of if cmd.actor.kind == "agent" else None
            if not roles & set(cmd.actor.roles) or (principal is not None and not roles & set(principal.roles)):
                return self._attempt(cmd, obj, "actor", f"{cmd.actor.id} may not {cmd.action}.", state)
            code, why = ("exists", f"{cmd.target} already exists.") if creating else ("not-found", f"No {obj} {cmd.target}.")
            return Decision(Outcome("rejected", code, why), (), ())

        meta = dict(at=at, actor=cmd.actor.ref(), domain_version=d.version,
                    on_behalf_of=cmd.on_behalf_of.ref() if cmd.on_behalf_of else None,
                    grant=cmd.grant.id if cmd.grant else None, thread_id=cmd.thread_id, run_id=cmd.run_id,
                    causation=cmd.causation, permissions=self._permissions(cmd))
        stream = cmd.target or ""

        def deny(code: str, reason: str) -> Decision:
            return self._attempt(cmd, obj, code, reason, state)

        current = state or {}
        view = ObjectView(d, obj, current, lookup)

        ok, why = self.actor_allowed(action, cmd, view)                                   # step 4
        if not ok:
            return deny("actor", why)

        tr = d.transitions.get(obj)
        if creating:                                                                        # no source state
            next_state = tr.initial if tr else None
        elif tr is not None:                                                                # step 5
            who = [cmd.actor] + ([cmd.on_behalf_of] if cmd.actor.kind == "agent" and cmd.on_behalf_of else [])
            c = self.cell(obj, current.get(tr.field), cmd.action, who)
            if c == "n/a":
                return deny("not-applicable", f"Not applicable when {current.get(tr.field)}.")
            if c == "undecided":
                return deny("undecided", "Undecided.")
            if isinstance(c, Deny):
                return deny("matrix", c.deny)
            next_state = c
        else:
            next_state = None

        from ..decl.rules import covering, meets  # step 5b (ADR-0048)
        frm = None if creating or tr is None else current.get(tr.field)
        principal = cmd.on_behalf_of if cmd.actor.kind == "agent" else None
        def rule_check(src: str) -> bool:                                                    # fail closed
            try:
                return evaluate(self._expr(src), self._env(view, cmd.actor, cmd.params, principal=principal)) is True
            except EvalError:
                return False
        for rid, rule in covering(d, cmd.action, frm):
            if not meets(rule, cmd.actor.kind, cmd.actor.roles, principal.roles if principal else None, rule_check):
                return deny(rid, rule.reason)

        for pre in action.preconditions:                                                    # step 6
            try:
                passed = evaluate(self._expr(pre.check), self._env(view, cmd.actor, cmd.params, principal=self._principal(cmd))) is True
            except EvalError as e:
                return deny(pre.id, f"{pre.reason} (could not evaluate: {e})")
            if not passed:
                return deny(pre.id, pre.reason)

        new = copy.deepcopy(current)                                                        # step 9
        changes: dict[str, Any] = {}
        if creating:
            # Only declared params that name a property or an outgoing link; never the state field.
            fields = set(d.objects[obj].properties) | {n for n, l in d.links.items() if l.from_ == obj}
            fields.discard(tr.field if tr else None)
            new = {"id": cmd.target, **{k: copy.deepcopy(v) for k, v in cmd.params.items()
                                        if k in action.params and k in fields}}
            changes.update(new)
        if tr is not None and next_state is not None:
            new[tr.field] = changes[tr.field] = next_state
        for eff in action.effects:
            if eff.call is not None:      # a kernel-service call: emitted after the append (step 12)
                continue
            if eff.create is not None:
                # Creating another object from an effect is not supported yet: fail closed.
                return Decision(Outcome("rejected", "unsupported-effect",
                                        f"create effects are not supported ({eff.create})", state), (), ())
            for key, value in (eff.set or {}).items():
                if key.startswith("new.") and not creating:
                    return Decision(Outcome("rejected", "unsupported-effect",
                                            f"{key}: `new.` is only valid in a create action", state), (), ())
                attr = key.split(".", 1)[1] if key.startswith(("target.", "new.")) else key
                if isinstance(value, str):
                    try:
                        value = evaluate(self._expr(value), self._env(view, cmd.actor, cmd.params, principal=self._principal(cmd)))
                    except EvalError as e:
                        return Decision(Outcome("rejected", "effect-error", f"{key}: {e}", state), (), ())
                if isinstance(value, datetime):
                    value = value.isoformat()
                new[attr] = changes[attr] = value

        for inv in self.violated_invariants(obj, new, lookup, cmd.actor, cmd.params):        # step 10
            ev = Event("InvariantGuardTriggered", stream, obj, kind="attempt",
                       payload={"action": cmd.action, "invariant": inv.id, "reason": inv.reason}, **meta)
            return Decision(Outcome("rejected", "invariant-guard", inv.reason, state), (), (ev,))

        etype = action.event or (f"{obj}Created" if creating else f"{obj}{_pascal(cmd.action)}")
        # Events own deep copies, so no caller can mutate history (replay parity).
        events = [Event(etype, stream, obj, payload=copy.deepcopy(
            {"changes": changes, "params": cmd.params, "action": cmd.action, "created": creating}), **meta)]
        if action.records_decision:
            events.append(Event("DecisionRecorded", stream, obj, kind="decision", payload=copy.deepcopy(
                {"action": cmd.action, "params": cmd.params, "inputs": current,
                 **({"rationale": cmd.params["rationale"]} if cmd.params.get("rationale") else {})}),
                **meta))
        events += self._handoffs(cmd, obj, new, lookup, meta)                              # step 12
        events += self._calls(cmd, action, obj, new, lookup, meta)
        return Decision(Outcome("ok", state=copy.deepcopy(new)), tuple(events), ())

    def _calls(self, cmd: Command, action: Action, obj: str, new: dict[str, Any], lookup: Lookup,
               meta: dict[str, Any]) -> list[Event]:
        """Kernel-service calls (ADR-0028), as outbox entries appended with the action. Inputs
        are evaluated on the resulting state; one that cannot be evaluated is recorded with its
        error, and the service then replies with a failure."""
        out = []
        view = ObjectView(self.d, obj, new, lookup)
        for k, eff in enumerate(action.effects):
            if eff.call is None:
                continue
            payload: dict[str, Any] = {"service": eff.call, "reply": eff.reply, "index": k, "inputs": {}, "error": None}
            try:
                env = self._env(view, cmd.actor, cmd.params, principal=self._principal(cmd))
                payload["inputs"] = {i: evaluate(self._expr(src), env) for i, src in eff.with_.items()}
                svc = CATALOG.get(eff.call)
                for i, v in payload["inputs"].items():
                    want = svc.inputs.get(i) if svc else None
                    if v is None and svc and i in svc.optional:
                        continue
                    if want and not _of_type(v, want):
                        raise EvalError(f"input '{i}' must be a {want}, got {v!r}")
            except EvalError as e:
                payload["error"] = str(e)
            out.append(Event("EffectRequested", cmd.target or "", obj, kind="outbox",
                             payload=copy.deepcopy(payload), **meta))
        return out

    def _handoffs(self, cmd: Command, obj: str, new: dict[str, Any], lookup: Lookup,
                  meta: dict[str, Any]) -> list[Event]:
        """Outbox entries, appended atomically with the sender's events and sent after the
        append (step 12). A mapping that cannot be evaluated is recorded with its error and
        never blocks the sender's action."""
        out = []
        view = ObjectView(self.d, obj, new, lookup)
        origin = origin_person(cmd)
        for name, h in self.d.handoffs.items():
            if h.when.action != cmd.action:
                continue
            payload: dict[str, Any] = {"handoff": name, "to": h.to.model_dump(), "origin": origin,
                                       "target": None, "params": {}, "error": None}
            try:
                env = self._env(view, cmd.actor, cmd.params, principal=self._principal(cmd))
                target = evaluate(self._expr(h.target), env)
                if not isinstance(target, str) or not target:
                    raise EvalError(f"target must be a non-empty string, got {target!r}")
                params = {k: evaluate(self._expr(src), env) for k, src in h.params.items()}
                payload.update(target=target, params=params)
            except EvalError as e:
                payload["error"] = str(e)
            out.append(Event("HandoffRequested", cmd.target or "", obj, kind="outbox",
                             payload=copy.deepcopy(payload), **meta))
        return out

    def violated_invariants(self, obj_type: str, state: Mapping[str, Any], lookup: Lookup,
                            actor: Actor | None = None, params: dict[str, Any] | None = None) -> list[Invariant]:
        """The aggregate invariants on `obj_type` that `state` breaks, in declaration order. An
        invariant that cannot be evaluated counts as broken (fail closed)."""
        view = ObjectView(self.d, obj_type, state, lookup)
        out = []
        for inv in self.d.invariants:
            if inv.on != obj_type or inv.scope != "aggregate":
                continue
            try:
                holds = evaluate(self._expr(inv.check), self._env(view, actor, params or {})) is True
            except EvalError:
                holds = False
            if not holds:
                out.append(inv)
        return out

    def _attempt(self, cmd: Command, obj: str, code: str, reason: str, state: Any) -> Decision:
        a = cmd.actor
        ev = Event("DeniedAttempt", cmd.target or "", obj, kind="attempt", at=cmd.at or self.clock(),
                   actor=a.ref() if a else None, domain_version=self.d.version,
                   on_behalf_of=cmd.on_behalf_of.ref() if cmd.on_behalf_of else None,
                   grant=cmd.grant.id if cmd.grant else None, thread_id=cmd.thread_id, run_id=cmd.run_id,
                   permissions=self._permissions(cmd),
                   payload=copy.deepcopy({"action": cmd.action, "code": code, "reason": reason, "params": cmd.params}))
        return Decision(Outcome("denied", code, reason, copy.deepcopy(state)), (), (ev,))

    @staticmethod
    def invalid_params(action: Action, params: dict[str, Any]) -> str | None:
        """Shape-check params against the declaration (ADR-0021). None if valid."""
        py = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "datetime": str}
        for name in params:
            if name not in action.params:
                return f"Unknown param '{name}'."
        for name, spec in action.params.items():
            if name not in params or params[name] is None:
                if not spec.optional:
                    return f"Missing param '{name}'."
                continue
            vals = params[name] if spec.many else [params[name]]
            if spec.many and not isinstance(params[name], list):
                return f"Param '{name}' must be a list."
            for v in vals:
                if (why := _unstorable(v)) is not None:
                    return f"Param '{name}' {why}."
                if spec.enum is not None and v not in spec.enum:
                    return f"Param '{name}' must be one of {spec.enum}."
                if spec.type is not None and (not isinstance(v, py[spec.type]) or
                                              (spec.type in ("integer", "number") and isinstance(v, bool))):
                    return f"Param '{name}' must be a {spec.type}."
                if spec.ref is not None and not isinstance(v, str):
                    return f"Param '{name}' must be an id of {spec.ref}."
        return None

    def allowed_actions(self, obj_type: str, state: dict[str, Any], actor: Actor, lookup: Lookup,
                        on_behalf_of: Actor | None = None, grant: Grant | None = None) -> list[str]:
        """Actions this actor could take now: steps 4-6, where preconditions that read
        `params` are skipped (they depend on the input and are checked at call time). An action
        listed here can succeed with valid params; one not listed cannot succeed with any.
        An agent is checked with its principal and grant, exactly as in `decide`."""
        out = []
        who = [actor] + ([on_behalf_of] if actor.kind == "agent" and on_behalf_of else [])
        view = ObjectView(self.d, obj_type, state, lookup)
        for name, a in self.d.actions.items():
            if a.target != obj_type:
                continue
            cmd = Command(actor, name, state.get("id"), {}, at=self.clock(), on_behalf_of=on_behalf_of, grant=grant)
            if not self.actor_allowed(a, cmd, view)[0]:
                continue
            tr = self.d.transitions.get(obj_type)
            if tr is not None:
                c = self.cell(obj_type, state.get(tr.field), name, who)
                if not isinstance(c, str) or c in ("n/a", "undecided"):
                    continue
            from ..decl.rules import covering, meets

            def rule_check(src: str) -> bool:      # a check that reads params is decided on submit
                if any(p.root == "params" for p in paths_read(self._expr(src))):
                    return True
                try:
                    return evaluate(self._expr(src), self._env(view, actor, {}, principal=on_behalf_of)) is True
                except EvalError:
                    return False
            if not all(meets(r, actor.kind, actor.roles, on_behalf_of.roles if on_behalf_of else None, rule_check)
                       for _, r in covering(self.d, name, state.get(tr.field) if tr else None)):
                continue
            ok = True
            for pre in a.preconditions:
                if any(p.root == "params" for p in paths_read(self._expr(pre.check))):
                    continue
                try:
                    ok = evaluate(self._expr(pre.check), self._env(view, actor, {}, principal=on_behalf_of)) is True
                except EvalError:
                    ok = False
                if not ok:
                    break
            if ok:
                out.append(name)
        return out
