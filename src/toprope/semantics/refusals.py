"""What a refused command says to do: the interpreter's gate refusals, with their fix (ADR-0053 §5,
which amends ADR-0049 §5).

The reasons a domain declares (a precondition's, a rule's, a matrix deny's, an invariant's) are the
domain's words: they are kept exactly, and a generic fix follows them (`fixed(…, verbatim=True)`).
A refusal only a person can resolve says to ask one; *how* a person takes the step is the
deployment's business, not the domain's, so it is added only when the caller is not a person and the
deployment names a route (`route`: for the self domains, `person_route:` in `toprope.yaml`, the human
request of ADR-0039). The harness and the TLA replay build the reason they expect with the same
functions, so the reasons stay one text.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..decl.models import ActorRule, ByRole, Deny, Domain, Target
from ..errors import fixed

ALLOWED = "take an action that `allowed` (CLI) or `allowed_actions` (MCP) lists for it"


def _via(route: str | None, kind: str = "agent") -> str:
    """How a person takes it, where the deployment says so; never told to a person themselves."""
    return f": {route}" if route and kind != "person" else ""


def _roles(rules: Any) -> str:
    out = [f"{r.role} where {r.where}" if isinstance(r, ActorRule) and r.where
           else (r.role if isinstance(r, ActorRule) else str(r)) for r in rules]
    if not out:
        return "no role yet"
    return f"the role {out[0]}" if len(out) == 1 else f"one of the roles {', '.join(out)}"


def by_person(action: str, route: str | None = None) -> str:
    return fixed(f"Only a person can {action}.", f"ask a person to take it{_via(route)}")


def not_allowed(who: str, action: str, rules: Any, kind: str = "person", route: str | None = None) -> str:
    """An actor without a role (or relation) the action allows."""
    return fixed(f"{who} may not {action}.", f"ask a person with {_roles(rules)} to take it{_via(route, kind)}")


def principal_not_allowed(principal: str, action: str, rules: Any, route: str | None = None) -> str:
    return fixed(f"Principal {principal} may not {action}.",
                 f"ask a person with {_roles(rules)} to take it{_via(route)}")


# -- the matrix (docs/semantics.md step 5) ------------------------------------------------------
def resolve(d: Domain, obj: str, state: Any, action: str, roles: Sequence[Sequence[str]]) -> Any:
    """A cell for the callers, each given by its roles (an agent and its principal): a target
    state, a Deny, "n/a" or "undecided". A `by_role` cell allows only if every role a caller holds
    that it lists allows the same target; otherwise the most restrictive outcome wins: deny, then
    n/a, then undecided (ADR-0021). The interpreter's `cell` is this."""
    c = d.transitions[obj].matrix.get(state, {}).get(action, "undecided")
    if isinstance(c, Target):
        return c.to
    if not isinstance(c, ByRole):
        return c
    outcomes: list[Any] = []
    for held in roles:
        outcomes += [c.by_role[r] for r in held if r in c.by_role] or ["n/a"]
    denies = [o for o in outcomes if isinstance(o, Deny)]
    if denies:
        return denies[0]
    for special in ("n/a", "undecided"):
        if special in outcomes:
            return special
    targets = {o.to if isinstance(o, Target) else o for o in outcomes}
    return targets.pop() if len(targets) == 1 else Deny(deny="Roles disagree on this transition.")


def _moves(c: Any) -> bool:
    return isinstance(c, (str, Target)) and c not in ("n/a", "undecided")


def _where(d: Domain, obj: str, action: str, roles: Sequence[Sequence[str]], state: Any) -> tuple[list[str], str]:
    """The roles the action applies for in this state (when the callers' roles are the cause), and
    the states it applies in for the callers."""
    tr = d.transitions[obj]
    mine = [s for s in tr.matrix if _moves(resolve(d, obj, s, action, roles))]
    cell = tr.matrix.get(state, {}).get(action)
    others = sorted(r for r, o in cell.by_role.items() if _moves(o)) if isinstance(cell, ByRole) else []
    return others, " or ".join(mine) or "no state, for your roles"


def not_applicable(d: Domain, obj: str, state: Any, action: str, roles: Sequence[Sequence[str]]) -> str:
    others, mine = _where(d, obj, action, roles, state)
    if others:
        return fixed(f"Not applicable when {state}.", f"{action} applies when the {obj} is {state} for "
                                                      f"{', '.join(others)}: ask a person with that role to take it")
    return fixed(f"Not applicable when {state}.", f"{action} applies when the {obj} is {mine}; move the {obj} "
                                                  f"there first, or {ALLOWED}")


def undecided(obj: str, state: Any, action: str) -> str:
    return fixed("Undecided.", f"the declaration has not decided `{action}` when the {obj} is {state}: decide that "
                               f"cell of {obj}'s transition matrix in the declaration (a person confirms it)")


def matrix_denied(d: Domain, obj: str, state: Any, action: str, reason: str,
                  roles: Sequence[Sequence[str]]) -> str:
    """A matrix cell that denies, in the domain's words."""
    others, mine = _where(d, obj, action, roles, state)
    if others:
        return fixed(reason, f"{action} applies when the {obj} is {state} for {', '.join(others)}: ask a person "
                             "with that role to take it", verbatim=True)
    return fixed(reason, f"{action} applies when the {obj} is {mine}; move the {obj} there first, or {ALLOWED}",
                 verbatim=True)


def rule_unmet(reason: str, requires: Any, kind: str = "person", route: str | None = None) -> str:
    """An outcome rule (ADR-0048) the actor does not meet, in the domain's words."""
    if requires == "human":
        return fixed(reason, f"ask a person to take it{_via(route, kind)}", verbatim=True)
    roles = list(getattr(requires, "roles", ()) or ())
    return fixed(reason, f"ask a person with {_roles(roles)} to take it{_via(route, kind)}", verbatim=True)


def _check(d: Domain | None, check: str) -> str:
    """The check, quoted, so the caller sees what must hold.
    TODO(M0b, read visibility): once a property can be hidden from a caller (`read`), a check that
    reads one must not be quoted to them. Until then no property can be hidden (`read` is refused at
    load), and this guard hides every check of a domain that declares `read` at all."""
    if d is not None and any(p.read is not None for o in d.objects.values() for p in o.properties.values()):
        return "its declared check"
    return f"`{check}`"


def precondition(reason: str, check: str, d: Domain | None = None) -> str:
    """A precondition that does not hold, in the domain's words."""
    return fixed(reason, f"the action is allowed when {_check(d, check)} holds; change the object or the params "
                         "first", verbatim=True)


def invariant(reason: str, check: str, d: Domain | None = None) -> str:
    """An invariant the result would break, in the domain's words."""
    return fixed(reason, f"the result must keep {_check(d, check)} true; change the params or the object first",
                 verbatim=True)
