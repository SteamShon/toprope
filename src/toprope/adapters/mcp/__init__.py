"""toprope-server's MCP surface: tools generated from the declaration (ADR-0017).

Every action tool calls `Execution.submit`, the single gate. Tool names, descriptions and
parameter types come from the declaration, so agents see the same terms and rules people do
(④). Denials are returned as results with a code and a reason in domain terms, not as errors.
The MCP SDK is isolated here, so a future SDK major version is a one-module change.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase, FuncMetadata
from pydantic import ConfigDict, Field, WithJsonSchema, create_model

from ...decl.models import Action, ActorRule, ByRole, Deny, Domain, Param, Target
from ...decl.validate import RESERVED_PARAMS
from ...exec import Execution
from ...identity import Caller
from ...types import Outcome

JSON_TYPE: dict[str, dict[str, Any]] = {
    "string": {"type": "string"}, "integer": {"type": "integer"}, "number": {"type": "number"},
    "boolean": {"type": "boolean"}, "datetime": {"type": "string", "format": "date-time"}}
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
    who = [r.role + (f" (where {r.where})" if r.where else "") if isinstance(r, ActorRule) else r
           for r in a.actor]
    parts = [a.description.rstrip(".") + ".", f"Who: {', '.join(who)}."]
    tr = d.transitions.get(a.object_type)
    if tr is not None and a.target:
        allowed: list[str] = []
        denied: set[str] = set()
        for state, cells in tr.matrix.items():
            c = cells.get(name)
            if isinstance(c, Target) or (isinstance(c, str) and c not in ("n/a", "undecided")):
                allowed.append(state)
            elif isinstance(c, Deny):
                denied.add(c.deny)
            elif isinstance(c, ByRole):
                roles = [r for r, o in c.by_role.items() if not isinstance(o, Deny)]
                if roles:
                    allowed.append(f"{state} (for {', '.join(roles)})")
                denied |= {o.deny for o in c.by_role.values() if isinstance(o, Deny)}
        if allowed:
            parts.append(f"Allowed when {tr.field} is {', '.join(allowed)}.")
        if denied:
            parts.append("Otherwise: " + " ".join(sorted(denied)))
    if a.preconditions:
        parts.append("Also requires: " + " ".join(p.reason for p in a.preconditions))
    if a.requires == "human":
        parts.append("Only a person can do this; agents are refused.")
    parts.append("Pass a unique idempotency_key and reuse it when retrying. A denial returns "
                 "status 'denied' with a code and a reason.")
    return " ".join(parts)


def param_schema(spec: Param) -> dict[str, Any]:
    """The JSON schema advertised for a declared param."""
    if spec.enum is not None:
        base: dict[str, Any] = {"type": "string", "enum": list(spec.enum)}
    elif spec.ref is not None:
        base = {"type": "string", "description": f"id of a {spec.ref}"}
    else:
        base = dict(JSON_TYPE[spec.type or "string"])
    if spec.many:
        base = {"type": "array", "items": base}
    return {"anyOf": [base, {"type": "null"}], "default": None} if spec.optional else base


class _StrictArgs(ArgModelBase):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


class _RawArgs(FuncMetadata):
    """Declared param values reach Execution exactly as sent: no JSON-in-string pre-parsing and no
    coercion ("5" stays a string, so Execution refuses it as it would refuse it directly)."""

    def pre_parse_json(self, data: dict[str, Any]) -> dict[str, Any]:
        return data


def build_server(ex: Execution, credentials: Credentials, *, harness: dict[str, Any] | None = None,
                 sources: Any = None, **server_kwargs: Any) -> MCPServer:
    """`harness` is a harness report (JSON) whose per-edge results the world map shows.
    `sources` is an authoring workspace: with it, `read_source` serves its sources' text."""
    from ...worldmap import build_world_map, how_to_reach as reach
    d = ex.d
    wmap = build_world_map(d, harness)
    for name, a in d.actions.items():
        clash = RESERVED_PARAMS & set(a.params)
        if clash:
            raise ValueError(f"action {name}: param name(s) {sorted(clash)} are reserved tool arguments")
    title = d.purpose.problem if d.purpose else None
    server = MCPServer(name=f"toprope:{d.domain}", title=title,
                       instructions=("Tools generated from the Toprope declaration "
                                     f"'{d.domain}' v{d.version}. Every action is checked against the "
                                     "transition matrix, roles, preconditions and invariants, and recorded."),
                       tools=[_action_tool(ex, credentials, n, a) for n, a in d.actions.items()],
                       **server_kwargs)

    def caller() -> Caller:
        c = ex.identity.resolve(credentials())
        if c is None:
            raise ToolError("Unknown or missing credentials.")
        return c

    def get_object(object_id: str) -> dict[str, Any]:
        """Current state of an object (a projection of its events)."""
        caller()
        st = ex.state(object_id)
        return st if st is not None else {"error": f"No object {object_id}."}

    def history(object_id: str) -> list[dict[str, Any]]:
        """Recorded domain and decision events for an object, oldest first."""
        caller()
        return [{"type": e.type, "version": e.version, "at": e.at.isoformat() if e.at else None,
                 "actor": e.actor, "on_behalf_of": e.on_behalf_of, "payload": e.payload}
                for e in ex.history(object_id)]

    def attempts(object_id: str) -> list[dict[str, Any]]:
        """Denied attempts and invariant-guard alarms recorded for an object."""
        caller()
        return [{"type": e.type, "at": e.at.isoformat() if e.at else None, "actor": e.actor,
                 "payload": e.payload} for e in ex.attempts(object_id)]

    def allowed_actions(object_id: str) -> list[str]:
        """Actions you could take on this object now (params-dependent checks apply at call time).
        For an agent, its principal and grant are applied."""
        return ex.allowed_actions(object_id, caller())

    def describe_domain() -> dict[str, Any]:
        """The domain's purpose, glossary, object types and actions: the shared vocabulary."""
        return {"domain": d.domain, "version": d.version,
                "purpose": d.purpose.model_dump(exclude_none=True) if d.purpose else None,
                "glossary": d.glossary,
                "objects": {n: {"description": o.description, "properties": sorted(o.properties)}
                            for n, o in d.objects.items()},
                "actions": {n: describe_action(d, n, a) for n, a in d.actions.items()}}

    def world_map() -> dict[str, Any]:
        """The whole domain as a map (ADR-0020): object types and links; states; one edge per
        (state, action) with its outcome, who unlocks it and what else it requires; fog where
        a cell is undecided; and the harness status of each edge."""
        return wmap

    def how_to_reach(object_id: str, target_state: str) -> dict[str, Any]:
        """The shortest sequence of actions that takes this object to `target_state`, who may
        take each step, and whether you can. Preconditions are listed, checked at call time."""
        c = caller()
        found = ex.lookup(object_id)
        if found is None:
            return {"reachable": False, "reason": f"No object {object_id}."}
        obj, st = found
        tr = d.transitions.get(obj)
        if tr is None:
            return {"reachable": False, "reason": f"{obj} has no states."}
        roles = set(c.actor.roles)
        if c.actor.kind == "agent":               # an agent can do only what its principal can
            roles &= set(c.on_behalf_of.roles) if c.on_behalf_of is not None else set()
        return reach(wmap, obj, st.get(tr.field), target_state, tuple(sorted(roles)))

    def read_source(source_id: str, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        """Read a source's chunks: redacted (secrets, personal data), each with the ref to cite
        in a proposal. A local-only source is refused. A read, not an action: what it serves is
        recorded in the workspace's usage log, never in an event log."""
        caller()
        from ...workspace import AuthoringError
        try:
            return sources.read_source(source_id, offset, max(1, min(limit, 50)))
        except AuthoringError as e:
            raise ToolError(str(e)) from None

    tools = [get_object, history, attempts, allowed_actions, describe_domain, world_map, how_to_reach]
    if sources is not None:
        tools.append(read_source)
    for fn in tools:
        server.add_tool(fn, name=fn.__name__)
    return server


def _action_tool(ex: Execution, credentials: Credentials, name: str, a: Action) -> Tool:
    """One tool per action. The argument model checks only the tool's own arguments and refuses
    unknown keys; declared params pass through untouched to `Execution.submit`, the one place
    that validates them, so MCP and direct calls decide identically. Declared names become
    aliases of synthetic fields, so any declared name works as an argument name."""
    target_param = "new_id" if a.creates else "target_id"
    fields: dict[str, Any] = {
        "f_target": (str, Field(alias=target_param)),
        "f_key": (str, Field(alias="idempotency_key")),
        "f_thread": (str | None, Field(None, alias="thread_id")),
        "f_run": (str | None, Field(None, alias="run_id")),
    }
    for i, (pname, spec) in enumerate(a.params.items()):
        ann = Annotated[Any, WithJsonSchema(param_schema(spec))]
        fields[f"p{i}"] = (ann, Field(None, alias=pname) if spec.optional else Field(alias=pname))
    model = create_model(f"{name}Arguments", __base__=_StrictArgs, **fields)

    def fn(**kw: Any) -> dict[str, Any]:
        target, key = kw.pop(target_param), kw.pop("idempotency_key")
        thread_id, run_id = kw.pop("thread_id", None), kw.pop("run_id", None)
        params = {k: v for k, v in kw.items() if v is not None}
        return outcome_json(ex.submit(credentials(), name, target, params, key, thread_id, run_id))

    def proto() -> dict[str, Any]: ...   # only for the SDK to derive the output schema
    out = Tool.from_function(proto, name=name).fn_metadata
    return Tool(fn=fn, name=name, description=describe_action(ex.d, name, a),
                parameters=model.model_json_schema(by_alias=True),
                fn_metadata=_RawArgs(arg_model=model, output_schema=out.output_schema,
                                     output_model=out.output_model, wrap_output=out.wrap_output),
                is_async=False)
