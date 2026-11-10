"""The natural-language check (ADR-0009), with an LLM reading the change as structure.

M1 measured the compiler without it, and an LLM reviewing the structured declarations with it
did better than either alone on rule conflicts (M1-report). This checker gives the LLM what the
compiler knows:
- the changed elements, before and after, as YAML;
- the capability diff (who can now reach what);
- the outcome rules;
- the whole new declaration.

It asks for conflicts with what the declaration states or plainly intends. Its findings are
warnings, never errors (ADR-0009).

A command runs the model, so any CLI works: the prompt goes on standard input, and the answer
comes back on standard output. `TOPROPE_NL_COMMAND` (for example
`claude -p --model <m> --tools ""`) turns it on for the kernel's change check.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from typing import Any

import yaml

from ..decl.models import Domain
from ..errors import fixed

ENV = "TOPROPE_NL_COMMAND"

PROMPT = """You review a change to a domain's declaration before it is deployed.

Find where the change conflicts with what the declaration states or plainly intends:
- a rule it goes around, for example a new way to reach a state that only a person should
  reach, or a step it skips that the declaration requires elsewhere;
- something that relied on what changed and no longer holds;
- a description, reason or rule that now contradicts the behaviour.
Report only conflicts this change introduces, each naming the element (`actions.<name>`,
`objects.<name>`, `rules.<id>`, ...).

Reply with JSON only: {"conflicts": [{"where": "actions.x", "problem": "what conflicts and with what"}]}
and an empty list when there is none.
"""


def _element(d: Domain | None, key: str) -> Any:
    if d is None:
        return None
    kind, _, name = key.partition(":")
    raw = d.model_dump(mode="json", by_alias=True, exclude_none=True)
    table = {"action": "actions", "object": "objects", "link": "links", "rule": "rules"}.get(kind)
    if table and name.split(".")[0] in raw.get(table, {}):
        return raw[table][name.split(".")[0]]
    return None


def build_prompt(old: Domain | None, new: Domain, changed: list[str]) -> str:
    from .capability import capability_diff
    parts = [PROMPT, "--- What changed (before → after) ---"]
    for key in changed:
        parts.append(f"## {key}\nbefore:\n{yaml.safe_dump(_element(old, key), sort_keys=False)}"
                     f"after:\n{yaml.safe_dump(_element(new, key), sort_keys=False)}")
    if old is not None:
        cap = [f"- {s}: {w}: {m}" for s, w, m in capability_diff(new, old) if s == "warning"]
        parts.append("--- Who can now reach what (the compiler's capability diff) ---\n" + ("\n".join(cap) or "(no widening)"))
    rules = getattr(new, "rules", None) or {}                  # outcome rules (ADR-0048), where the schema has them
    parts.append("--- Outcome rules ---\n" + (yaml.safe_dump(
        {k: v.model_dump(mode="json", exclude_none=True) for k, v in rules.items()}, sort_keys=False) if rules else "(none)"))
    parts.append("--- The whole declaration after the change ---\n" +
                 yaml.safe_dump(new.model_dump(mode="json", by_alias=True, exclude_none=True), sort_keys=False, allow_unicode=True))
    return "\n\n".join(parts)


def parse(text: str) -> list[tuple[str, str]]:
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            data, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("conflicts"), list):
            return [(str(c.get("where", "")), str(c.get("problem", ""))) for c in data["conflicts"] if isinstance(c, dict)]
    raise ValueError(fixed("the checker did not answer with the JSON asked for",
                           "run the check again; if it repeats, check the checker command's prompt handling"))


class CommandChecker:
    """An `NLChecker` that runs a command with the prompt on standard input."""

    def __init__(self, command: str | list[str], timeout: float = 600):
        self.command = shlex.split(command) if isinstance(command, str) else list(command)
        self.timeout = timeout

    def conflicts(self, old: Domain | None, new: Domain, changed: list[str]) -> list[tuple[str, str]]:
        if not changed:
            return []
        r = subprocess.run(self.command, input=build_prompt(old, new, changed), capture_output=True, text=True,
                           timeout=self.timeout, check=False)
        if r.returncode != 0:
            raise RuntimeError(fixed(f"the checker exited {r.returncode}: {r.stderr.strip()[-500:]}",
                                     "fix the checker command (its error is above), or run the check without the "
                                     "language check"))
        return parse(r.stdout)


def from_env() -> CommandChecker | None:
    cmd = os.environ.get(ENV, "").strip()
    return CommandChecker(cmd) if cmd else None
