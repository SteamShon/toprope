"""One role's conversation: a fresh context, its prompt, its materials, its tools (ADR-0040 §1).

Every request and reply is written to a transcript, so a run can be read back and scored.
File tools are confined to one directory: a role never reads outside its arm's workspace.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import Model


@dataclass
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    fn: Callable[..., Any]

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}


class Transcript:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, **data: Any) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps({"at": time.time(), "kind": kind, **data}, ensure_ascii=False, default=str) + "\n")


def text_of(reply: dict[str, Any]) -> str:
    return "\n".join(b.get("text", "") for b in reply.get("content", []) if b.get("type") == "text").strip()


def converse(model: Model, system: str, user: str, tools: list[Tool], transcript: Transcript,
             max_turns: int = 40, progress: Callable[[str], None] | None = None) -> str:
    """Run until the model answers without calling a tool; return that answer's text."""
    by_name = {t.name: t for t in tools}
    specs = [t.spec() for t in tools]
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    transcript.write("start", system=system, user=user, tools=[t.name for t in tools])
    for turn in range(1, max_turns + 1):
        reply = model(system, messages, specs)
        if progress:
            progress(f"turn {turn}")
        transcript.write("reply", content=reply.get("content"), stop_reason=reply.get("stop_reason"),
                         usage=reply.get("usage"))
        messages.append({"role": "assistant", "content": reply.get("content", [])})
        uses = [b for b in reply.get("content", []) if b.get("type") == "tool_use"]
        if not uses:
            return text_of(reply)
        results = []
        for u in uses:
            tool = by_name.get(u["name"])
            try:
                if tool is None:
                    raise ToolError(f"no tool {u['name']!r}")
                out, error = tool.fn(**(u.get("input") or {})), False
            except ToolError as e:
                out, error = str(e), True
            except TypeError as e:                              # wrong arguments from the model
                out, error = f"bad arguments: {e}", True
            content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
            transcript.write("tool", name=u["name"], input=u.get("input"), output=content, error=error)
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": content, "is_error": error})
        messages.append({"role": "user", "content": results})
    transcript.write("stopped", reason=f"no answer after {max_turns} turns")
    return ""


class ToolError(Exception):
    """A tool refused; the model sees the message and may try again."""


def confined(root: Path, rel: str) -> Path:
    """`rel` inside `root`, or a ToolError: no absolute paths, no `..`, no symlinks out."""
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
        raise ToolError("give a path relative to the workspace")
    p = (root / rel).resolve()
    if p != root.resolve() and root.resolve() not in p.parents:
        raise ToolError(f"{rel} is outside the workspace")
    return p


def file_tools(root: Path) -> list[Tool]:
    """List, read and write files inside `root`, and nothing else."""
    def list_files() -> list[str]:
        return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())

    def read_file(path: str) -> str:
        p = confined(root, path)
        if not p.is_file():
            raise ToolError(f"no file {path}")
        return p.read_text()

    def write_file(path: str, content: str) -> str:
        p = confined(root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {path} ({len(content)} characters)"

    def replace_in_file(path: str, old: str, new: str) -> str:
        p = confined(root, path)
        if not p.is_file():
            raise ToolError(f"no file {path}")
        text = p.read_text()
        n = text.count(old)
        if n != 1:
            raise ToolError(f"`old` occurs {n} times in {path}; give text that occurs exactly once")
        p.write_text(text.replace(old, new))
        return f"replaced in {path}"

    s = {"type": "string"}
    return [
        Tool("list_files", "List the files in the workspace.", {"type": "object", "properties": {}}, list_files),
        Tool("read_file", "Read a file in the workspace.",
             {"type": "object", "properties": {"path": s}, "required": ["path"]}, read_file),
        Tool("write_file", "Write a whole file in the workspace.",
             {"type": "object", "properties": {"path": s, "content": s}, "required": ["path", "content"]}, write_file),
        Tool("replace_in_file", "Replace text that occurs exactly once in a file.",
             {"type": "object", "properties": {"path": s, "old": s, "new": s}, "required": ["path", "old", "new"]},
             replace_in_file),
    ]
