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


@dataclass(frozen=True)
class ToolSpec:
    kind: str
    root: str
    context: str = "{}"                 # JSON: what the kind's tools need besides the root

    def __post_init__(self) -> None:
        # The tools may run in another process and directory (the CLI backend's MCP server):
        # a relative root would name a different, empty directory there.
        object.__setattr__(self, "root", str(Path(self.root).resolve()))

    def dumps(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def loads(cls, text: str) -> ToolSpec:
        return cls(**json.loads(text))

    def names(self) -> list[str]:
        return [t.name for t in build_tools(self)]


def build_tools(spec: ToolSpec) -> list[Tool]:
    """A role's tools, checked for experiment words, with the workspace's absolute path kept out
    of every result and error (run protocol §1)."""
    from .blind import check_files, check_tools, redact
    tools = _build(spec)
    check_tools(tools)
    root = Path(spec.root)
    if spec.kind == "files" and root.is_dir():
        check_files(root)

    def guarded(fn):
        @functools.wraps(fn)
        def call(*a, **k):
            try:
                return redact(fn(*a, **k), root)
            except ToolError as e:
                raise ToolError(redact(str(e), root)) from None
        return call

    return [Tool(t.name, t.description, t.schema, guarded(t.fn)) for t in tools]


def _build(spec: ToolSpec) -> list[Tool]:
    if spec.kind == "files":
        return file_tools(Path(spec.root))
    if spec.kind == "probe":
        from .probes import probe_tools
        return probe_tools(Path(spec.root), json.loads(spec.context))
    if spec.kind == "toprope":
        from .toprope_arm import toprope_tools
        return toprope_tools(Path(spec.root), json.loads(spec.context))
    raise ValueError(f"no tool kind {spec.kind!r}")


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
