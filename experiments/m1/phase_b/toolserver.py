"""The harness's tools for one role, served over MCP to a `claude -p` conversation.

A role's tools are named by a `ToolSpec` (a kind and a root), so that the same tools can be
built in-process (the API backend) or in this server (the CLI backend):

  python -m phase_b.toolserver '{"kind": "files", "root": "/path/to/workspace"}'
"""

from __future__ import annotations

import functools
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .agent import Tool, ToolError, file_tools

SERVER = "phase_b"
KINDS = {"files": file_tools}


@dataclass(frozen=True)
class ToolSpec:
    kind: str
    root: str

    def dumps(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def loads(cls, text: str) -> ToolSpec:
        return cls(**json.loads(text))

    def names(self) -> list[str]:
        return [t.name for t in build_tools(self)]


def build_tools(spec: ToolSpec) -> list[Tool]:
    if spec.kind not in KINDS:
        raise ValueError(f"no tool kind {spec.kind!r}")
    return KINDS[spec.kind](Path(spec.root))


def make_server(spec: ToolSpec):
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError as McpToolError

    def wrap(fn):
        @functools.wraps(fn)
        def call(*a, **k):
            try:
                out = fn(*a, **k)
            except ToolError as e:
                raise McpToolError(str(e)) from None
            return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return call

    server = MCPServer(SERVER)
    for t in build_tools(spec):
        server.add_tool(wrap(t.fn), name=t.name, description=t.description, structured_output=False)
    return server


def serve(spec: ToolSpec) -> None:
    make_server(spec).run("stdio")

if __name__ == "__main__":
    serve(ToolSpec.loads(sys.argv[1]))
