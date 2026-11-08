"""Where a role's conversation runs (ADR-0040 §1, as amended).

  CliBackend  the researcher's own Claude Code, one `claude -p` per conversation, on their
              machine (the default: no key, the researcher's subscription)
  ApiBackend  the model API, through `model.py` (tests use it with a fake model)

Both give a role the same things: its prompt, its message, and the harness's tools for it,
named by a `ToolSpec` and nothing else.

How the CLI backend keeps a role blind:
- Claude Code's built-in tools are off (`--tools ""`): no file reads, no shell.
- The role's tools are served by `toolserver.py` over MCP, and only they are loaded
  (`--strict-mcp-config`). They are confined to the arm's workspace.
- The system prompt is the role's prompt (`--system-prompt`), not Claude Code's.
- It runs in a fresh, empty directory outside the repository, so no project CLAUDE.md or
  project settings load (`--setting-sources local`; there is no local settings file there).
- The run checks, before it starts, that there is no user memory (`~/.claude/CLAUDE.md`).
- The init event lists the tools the conversation got; anything but the role's tools stops the
  run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import Transcript, converse
from .model import Model, Usage
from .toolserver import SERVER, ToolSpec, build_tools

Progress = Callable[[str], None]


def extra_servers(tools: ToolSpec) -> dict[str, Any]:
    """MCP servers besides the harness's own, named in a ToolSpec's context (the Toprope arm's
    probes: the generated servers of the deployed domains)."""
    return json.loads(tools.context or "{}").get("servers") or {}


class UsageLimit(RuntimeError):
    """The subscription's usage limit was reached; run again later to continue."""


class BackendError(RuntimeError):
    pass


@dataclass
class Backend:
    usage: Usage = field(default_factory=Usage)
    usd: float = 0.0                                         # an estimate; not a bill for a subscription
    progress: Progress | None = None
    _lock: Any = field(default_factory=threading.Lock, repr=False, compare=False)

    def converse(self, system: str, user: str, tools: ToolSpec | None, transcript: Transcript,
                 max_turns: int = 40) -> str:
        raise NotImplementedError

    def report(self) -> dict[str, Any]:
        u = self.usage
        return {"tokens": {"input": u.input, "output": u.output, "cache_write": u.cache_write,
                           "cache_read": u.cache_read}, "usd_estimate": round(self.usd, 4)}

    def _say(self, text: str) -> None:
        if self.progress:
            self.progress(text)


class ApiBackend(Backend):
    def __init__(self, model: Model, budget: Any = None, progress: Progress | None = None):
        super().__init__(progress=progress)
        self.model, self.budget = model, budget

    def converse(self, system, user, tools, transcript, max_turns=40):
        if tools is not None and extra_servers(tools):
            raise BackendError("the API backend cannot reach MCP servers; use the cli backend")
        out = converse(self.model, system, user, build_tools(tools) if tools else [], transcript, max_turns,
                       progress=self._say)
        if self.budget:
            with self._lock:
                self.usage, self.usd = self.budget.used, self.budget.cost()
        return out


def user_memory() -> Path | None:
    """The user-level CLAUDE.md that Claude Code would add to every conversation, if any."""
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    p = base / "CLAUDE.md"
    return p if p.is_file() and p.read_text().strip() else None


# The subscription's limits only: a transient rate limit or overload is not one of them.
LIMIT_WORDS = ("usage limit", "session limit", "weekly limit", "hit your limit")


class CliBackend(Backend):
    def __init__(self, model: str, claude: str = "claude", progress: Progress | None = None):
        super().__init__(progress=progress)
        if not model:
            raise SystemExit("give --model: the model under test (ADR-0040 §7)")
        if shutil.which(claude) is None:
            raise SystemExit(f"`{claude}` is not on PATH: install Claude Code and log in first")
        self.model, self.claude = model, claude

    def command(self, system: str, mcp_config: Path | None, max_turns: int,
                servers: tuple[str, ...] = (SERVER,)) -> list[str]:
        cmd = [self.claude, "-p", "--model", self.model, "--system-prompt", system, "--tools", "",
               "--strict-mcp-config", "--setting-sources", "local", "--output-format", "stream-json",
               "--verbose", "--max-turns", str(max_turns), "--no-session-persistence"]
        if mcp_config is not None:
            cmd += ["--mcp-config", str(mcp_config), "--allowedTools", *(f"mcp__{s}" for s in servers)]
        return cmd

    def converse(self, system, user, tools, transcript, max_turns=40):
        # stderr goes to a file, not a pipe: a full pipe would block claude while we read stdout
        with tempfile.TemporaryDirectory(prefix="work-") as tmp, tempfile.TemporaryFile(mode="w+") as errfile:
            cwd = Path(tmp)
            cfg = None
            if tools is not None:
                cfg = cwd.parent / f"{cwd.name}.mcp.json"
                cfg.write_text(json.dumps({"mcpServers": {SERVER: {
                    "command": sys.executable, "args": ["-m", "phase_b.toolserver", tools.dumps()],
                    "env": {"PYTHONPATH": str(Path(__file__).resolve().parents[1])}}, **extra_servers(tools)}}))
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # the subscription
            transcript.write("start", system=system, user=user, tools=tools.kind if tools else None,
                             backend="claude-cli")
            try:
                names = (SERVER, *extra_servers(tools)) if tools is not None else ()
                return self._run(self.command(system, cfg, max_turns, names), user, cwd, env, tools, transcript,
                                 errfile)
            finally:
                if cfg is not None:
                    cfg.unlink(missing_ok=True)

    def _run(self, cmd, user, cwd, env, tools, transcript, errfile) -> str:
        allowed = {f"mcp__{SERVER}__{n}" for n in (tools.names() if tools else [])}
        prefixes = tuple(f"mcp__{s}__" for s in extra_servers(tools)) if tools else ()
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=errfile, text=True)
        assert p.stdin and p.stdout
        p.stdin.write(user)
        p.stdin.close()
        result: dict[str, Any] | None = None
        turns, t0 = 0, time.monotonic()
        try:
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = ev.get("type")
                if kind == "system" and ev.get("subtype") == "init":
                    got = set(ev.get("tools") or [])
                    other = {n for n in got - allowed if not (prefixes and n.startswith(prefixes))}
                    if other:
                        p.kill()
                        transcript.write("refused", tools=sorted(got))
                        raise BackendError(f"the conversation got tools it must not have: {sorted(other)}")
                    transcript.write("init", tools=sorted(got), model=ev.get("model"))
                elif kind == "assistant":
                    turns += 1
                    msg = ev.get("message") or {}
                    transcript.write("reply", content=msg.get("content"), usage=msg.get("usage"))
                    self._say(f"turn {turns} · {int(time.monotonic() - t0)}s")
                elif kind == "user":
                    for b in (ev.get("message") or {}).get("content") or []:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            transcript.write("tool", output=b.get("content"), error=b.get("is_error", False))
                elif kind == "result":
                    result = ev
        finally:
            p.wait()
            errfile.seek(0)
            err = errfile.read()
        if result is None:
            text = err.strip()[-2000:]
            if any(w in text.lower() for w in LIMIT_WORDS):
                raise UsageLimit(text)
            raise BackendError(f"claude exited {p.returncode} without a result: {text}")
        transcript.write("result", subtype=result.get("subtype"), is_error=result.get("is_error"),
                         result=result.get("result"), usage=result.get("usage"),
                         usd_estimate=result.get("total_cost_usd"), turns=result.get("num_turns"))
        with self._lock:                                  # probes run in parallel threads
            self.usage = self.usage + Usage.of(result.get("usage") or {})
            self.usd += float(result.get("total_cost_usd") or 0)
        text = str(result.get("result") or "")
        if result.get("is_error"):
            if any(w in text.lower() for w in LIMIT_WORDS):
                raise UsageLimit(text)
            if result.get("subtype") == "error_max_turns":
                transcript.write("stopped", reason="max turns")
                return ""
            raise BackendError(f"the conversation failed: {result.get('subtype')}: {text[:500]}")
        return text
