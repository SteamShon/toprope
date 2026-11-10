"""What a refused command says to do (ADR-0049 §5): the interpreter's gate refusals, with their fix.

The reasons a domain declares (a precondition's, a rule's, a matrix deny's, an invariant's) are the
domain's words and stay as written; the fix after them is generic. The harness and the TLA replay
build the reason they expect with the same functions, so the reasons stay one text.
"""

from __future__ import annotations

from typing import Any

from ..decl.models import ActorRule, Domain
from ..errors import fixed

# Only a person can resolve these: how a person takes the step (ADR-0039).
VIA = ("on their terminal, or from a cloud session through a human request they approve in GitHub "
       "(`toprope-change` writes one for a change; `tools/human_request.py` for any step)")
ASK_A_PERSON = f"ask a person to take it: {VIA}"


def by_person(action: str) -> str:
    return fixed(f"Only a person can {action}.", ASK_A_PERSON)


def _rules(rules: Any) -> str:
    out = [f"{r.role} where {r.where}" if isinstance(r, ActorRule) and r.where
           else (r.role if isinstance(r, ActorRule) else str(r)) for r in rules]
    return ", ".join(out) or "no role"


def not_allowed(who: str, action: str, rules: Any) -> str:
    """An actor without a role (or relation) the action allows."""
    return fixed(f"{who} may not {action}.",
                 f"{action} is for {_rules(rules)}; ask a person who holds that role to take it: {VIA}")


def principal_not_allowed(principal: str, action: str, rules: Any) -> str:
    return fixed(f"Principal {principal} may not {action}.",
                 f"{action} is for {_rules(rules)}, and the person an agent works for must hold it too; "
                 f"ask a person who holds that role to take it: {VIA}")


def applies_in(d: Domain, obj: str, action: str) -> list[str]:
    """The states from which the action's matrix cell moves the object, for some role."""
    from ..decl.rules import _to
    tr = d.transitions.get(obj)
    if tr is None:
        return []
    return [s for s, row in tr.matrix.items() if _to(row.get(action))]


def _states(d: Domain, obj: str, action: str) -> str:
    states = applies_in(d, obj, action)
    return f"when the {obj} is {' or '.join(states)}" if states else "from no state yet"


def not_applicable(d: Domain, obj: str, state: Any, action: str) -> str:
    return fixed(f"Not applicable when {state}.",
                 f"{action} applies {_states(d, obj, action)}; move the {obj} there first, or take an action "
                 "that `allowed` (CLI) or `allowed_actions` (MCP) lists for it")


def undecided(obj: str, state: Any, action: str) -> str:
    return fixed("Undecided.", f"the declaration has not decided `{action}` when the {obj} is {state}: decide that "
                               f"cell of {obj}'s transition matrix in the declaration (a person confirms it)")


def matrix_denied(d: Domain, obj: str, state: Any, action: str, reason: str) -> str:
    """A matrix cell that denies, in the domain's words."""
    return fixed(reason, f"{action} is denied when the {obj} is {state}; it applies {_states(d, obj, action)}")


def rule_unmet(reason: str, requires: Any) -> str:
    """An outcome rule (ADR-0048) the actor does not meet, in the domain's words."""
    if requires == "human":
        return fixed(reason, ASK_A_PERSON)
    roles = ", ".join(getattr(requires, "roles", ()) or ()) or "a role the rule names"
    return fixed(reason, f"this outcome is for {roles}; ask a person who holds that role to take it: {VIA}")


def precondition(reason: str, check: str) -> str:
    """A precondition that does not hold, in the domain's words."""
    return fixed(reason, f"the action is allowed when `{check}`; change the object or the params first")


def invariant(reason: str, check: str) -> str:
    """An invariant the result would break, in the domain's words."""
    return fixed(reason, f"the result must keep `{check}` true; change the params or the object first")
