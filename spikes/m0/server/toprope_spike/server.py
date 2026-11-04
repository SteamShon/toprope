"""Spike: generate MCP tools from a declaration and serve them (ADR-0017 toprope-server shape)."""
from __future__ import annotations

import inspect
import sys
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

from .kernel import Actor, Domain

PY = {"string": str, "integer": int, "number": float, "boolean": bool}


def build_server(domain: Domain) -> MCPServer:
    decl = domain.decl
    server = MCPServer(name=f"toprope:{decl['domain']}",
                       instructions="Generated from a Toprope declaration. Every action is checked "
                                    "against the transition matrix, roles, preconditions and invariants.")

    def make_action_tool(action: str, spec: dict[str, Any]):
        def fn(**kwargs: Any) -> dict[str, Any]:
            actor = Actor(id=kwargs.pop("actor_id"), role=kwargs.pop("actor_role"))
            target = kwargs.pop("target_id")
            params = {k: v for k, v in kwargs.items() if v is not None}
            return domain.execute(action, target, actor, params).as_dict()

        sig_params = [
            inspect.Parameter("target_id", inspect.Parameter.KEYWORD_ONLY, annotation=str),
            # Spike only: identity comes from the Identity port (ADR-0016) in the real server.
            inspect.Parameter("actor_id", inspect.Parameter.KEYWORD_ONLY, annotation=str),
            inspect.Parameter("actor_role", inspect.Parameter.KEYWORD_ONLY, annotation=str),
        ]
        for pname, pspec in (spec.get("params") or {}).items():
            t = PY[pspec["type"]]
            if pspec.get("optional"):
                sig_params.append(inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY,
                                                    annotation=Optional[t], default=None))
            else:
                sig_params.append(inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY, annotation=t))
        fn.__signature__ = inspect.Signature(sig_params, return_annotation=dict[str, Any])  # type: ignore[attr-defined]
        fn.__annotations__ = {p.name: p.annotation for p in sig_params} | {"return": dict[str, Any]}
        fn.__name__ = action
        # Description generated from the declaration: meaning, who may act, what can stop it.
        reasons = [p["reason"] for p in spec.get("preconditions", [])]
        desc = (f"{spec['description']} Allowed roles: {', '.join(spec.get('actor', []))}."
                + (f" Requires: {' '.join(reasons)}" if reasons else "")
                + " Denials return a reason in domain terms.")
        server.add_tool(fn, name=action, description=desc)

    for action, spec in decl["actions"].items():
        make_action_tool(action, spec)

    def get_object(object_id: str) -> dict[str, Any]:
        """Current projected state of an object."""
        return domain.project(object_id) or {"error": f"No object {object_id}."}

    def world_map(role: Optional[str] = None) -> dict[str, Any]:
        """The domain's world map: every (state, action) cell with its outcome and unlock requirements."""
        return domain.world_map(role)

    def history(object_id: str) -> dict[str, Any]:
        """Read-only event history for an object: domain events and attempts (denials, decisions)."""
        return {"events": domain.store.streams.get(object_id, []),
                "attempts": domain.store.attempts.get(object_id, [])}

    server.add_tool(get_object, name="get_object")
    server.add_tool(world_map, name="world_map")
    server.add_tool(history, name="history")
    return server


def main() -> None:
    decl = sys.argv[1] if len(sys.argv) > 1 else "toy.domain.yaml"
    transport = sys.argv[2] if len(sys.argv) > 2 else "streamable-http"
    server = build_server(Domain(decl))
    if transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
