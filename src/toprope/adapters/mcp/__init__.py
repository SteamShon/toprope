"""toprope-server's MCP surface: tools generated from the declaration (ADR-0017).

Every action tool calls `Execution.submit`, the single gate. Tool names, descriptions and
parameter types come from the declaration, so agents see the same terms and rules people do
(④). Denials are returned as results with a code and a reason in domain terms, not as errors.
The MCP SDK is isolated here, so a future SDK major version is a one-module change.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Literal, Optional

from mcp.server.mcpserver import MCPServer

from ...decl.models import Action, ActorRule, Deny, Domain
from ...exec import Execution
from ...types import Outcome

PY: dict[str, Any] = {"string": str, "integer": int, "number": float, "boolean": bool, "datetime": str}
Credentials = Callable[[], "str | None"]


def outcome_json(o: Outcome) -> dict[str, Any]:
    out: dict[str, Any] = {"status": o.status}
    if o.code:
        out["code"] = o.code
    if o.reason:
        out["reason"] = o.reason
    if o.state is not None:
        out["state"] = o.state
    return out


def describe_action(d: Domain, name: str, a: Action) -> str:
    """A tool description built only from the declaration's own words."""
    roles = ", ".join(r.role if isinstance(r, ActorRule) else r for r in a.actor)
    parts = [a.description.rstrip(".") + ".", f"Who: {roles}."]
    tr = d.transitions.get(a.object_type)
    if tr is not None and a.target:
        allowed = [s for s, cells in tr.matrix.items()
                   if isinstance(cells.get(name), str) and cells[name] not in ("n/a", "undecided")]
        if allowed:
            parts.append(f"Allowed when {tr.field} is {', '.join(allowed)}.")
        denied = {c.deny for c in (cells.get(name) for cells in tr.matrix.values()) if isinstance(c, Deny)}
        if denied:
            parts.append("Otherwise: " + " ".join(sorted(denied)))
    if a.preconditions:
        parts.append("Also requires: " + " ".join(p.reason for p in a.preconditions))
    if a.requires == "human":
        parts.append("Only a person can do this; agents are refused.")
    parts.append("Pass a unique idempotency_key and reuse it when retrying. A denial returns "
                 "status 'denied' with a code and a reason.")
    return " ".join(parts)


def _param_annotation(spec) -> Any:
    base: Any = Literal[tuple(spec.enum)] if spec.enum else (str if spec.ref else PY[spec.type])
    if spec.many:
        base = list[base]
    return Optional[base] if spec.optional else base


def build_server(ex: Execution, credentials: Credentials, **server_kwargs: Any) -> MCPServer:
    d = ex.d
    title = d.purpose.problem if d.purpose else None
    server = MCPServer(name=f"toprope:{d.domain}", title=title,
                       instructions=("Tools generated from the Toprope declaration "
                                     f"'{d.domain}' v{d.version}. Every action is checked against the "
                                     "transition matrix, roles, preconditions and invariants, and recorded."),
                       **server_kwargs)

    for name, a in d.actions.items():
        server.add_tool(_action_tool(ex, credentials, name, a), name=name,
                        description=describe_action(d, name, a))

    def get_object(object_id: str) -> dict[str, Any]:
        """Current state of an object (a projection of its events)."""
        st = ex.state(object_id)
        return st if st is not None else {"error": f"No object {object_id}."}

    def history(object_id: str) -> list[dict[str, Any]]:
        """Recorded domain and decision events for an object, oldest first."""
        return [{"type": e.type, "version": e.version, "at": e.at.isoformat() if e.at else None,
                 "actor": e.actor, "on_behalf_of": e.on_behalf_of, "payload": e.payload}
                for e in ex.history(object_id)]

    def attempts(object_id: str) -> list[dict[str, Any]]:
        """Denied attempts and invariant-guard alarms recorded for an object."""
        return [{"type": e.type, "at": e.at.isoformat() if e.at else None, "actor": e.actor,
                 "payload": e.payload} for e in ex.attempts(object_id)]

    def allowed_actions(object_id: str) -> list[str]:
        """Actions you could take on this object now (params-dependent checks apply at call time)."""
        caller = ex.identity.resolve(credentials())
        return [] if caller is None else ex.allowed_actions(object_id, caller.actor)

    def describe_domain() -> dict[str, Any]:
        """The domain's purpose, glossary, object types and actions: the shared vocabulary."""
        return {"domain": d.domain, "version": d.version,
                "purpose": d.purpose.model_dump(exclude_none=True) if d.purpose else None,
                "glossary": d.glossary,
                "objects": {n: {"description": o.description, "properties": sorted(o.properties)}
                            for n, o in d.objects.items()},
                "actions": {n: describe_action(d, n, a) for n, a in d.actions.items()}}

    for fn in (get_object, history, attempts, allowed_actions, describe_domain):
        server.add_tool(fn, name=fn.__name__)
    return server


def _action_tool(ex: Execution, credentials: Credentials, name: str, a: Action):
    target_param = "new_id" if a.creates else "target_id"

    def fn(**kw: Any) -> dict[str, Any]:
        target = kw.pop(target_param)
        key = kw.pop("idempotency_key")
        thread_id, run_id = kw.pop("thread_id", None), kw.pop("run_id", None)
        params = {k: v for k, v in kw.items() if v is not None}
        return outcome_json(ex.submit(credentials(), name, target, params, key, thread_id, run_id))

    P = inspect.Parameter
    sig = [P(target_param, P.KEYWORD_ONLY, annotation=str),
           P("idempotency_key", P.KEYWORD_ONLY, annotation=str)]
    for pname, spec in a.params.items():
        ann = _param_annotation(spec)
        sig.append(P(pname, P.KEYWORD_ONLY, annotation=ann, **({"default": None} if spec.optional else {})))
    sig += [P("thread_id", P.KEYWORD_ONLY, annotation=Optional[str], default=None),
            P("run_id", P.KEYWORD_ONLY, annotation=Optional[str], default=None)]
    fn.__signature__ = inspect.Signature(sig, return_annotation=dict[str, Any])  # type: ignore[attr-defined]
    fn.__annotations__ = {p.name: p.annotation for p in sig} | {"return": dict[str, Any]}
    fn.__name__ = name
    return fn
