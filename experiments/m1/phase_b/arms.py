"""The arms of Phase B (docs/experiments/M1-self-compile.md, ADR-0040 §3).

An arm takes one change request at a time and goes through the same three steps:

  edit    an editor applies the request to the arm's files
  check   the arm's pre-deploy check reports findings
  deploy  the change goes out, flagged or not (ADR-0040 §4)

The natural-language arm and the structured-spec arm are both text arms: they differ only in
their files (a SKILL.md, or the YAML declarations given as text) and in how the prompts name
them. Their check is an LLM review of the diff against every file. The Toprope arm (a sandbox
with the compiler's checks) is a separate module.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import Transcript, converse, file_tools
from .model import Model

PROMPTS = Path(__file__).parent / "prompts"


def prompt(name: str, **fill: str) -> str:
    text = (PROMPTS / f"{name}.md").read_text()
    for k, v in fill.items():
        text = text.replace("{" + k + "}", v)
    return text


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


def diff(before: dict[str, str], after: dict[str, str]) -> str:
    out = []
    for name in sorted(set(before) | set(after)):
        a, b = before.get(name, ""), after.get(name, "")
        if a != b:
            out += difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True),
                                        f"a/{name}", f"b/{name}")
    return "".join(out)


def request_text(req: dict[str, Any]) -> str:
    return f"Change request {req['seq']}: {req['intent']}\nWhy: {req.get('rationale', '').strip()}"


def parse_findings(text: str) -> tuple[list[dict[str, Any]], str | None]:
    """The reviewer's findings, and an error when its answer was not the JSON asked for."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return [], "the review did not answer with the JSON asked for"
    return [f for f in data["findings"] if isinstance(f, dict)], None


@dataclass
class StepResult:
    seconds: float
    data: dict[str, Any] = field(default_factory=dict)


class TextArm:
    """An arm whose domain is a set of text files, checked by an LLM review."""

    def __init__(self, name: str, described: str, materials: Path, work: Path, model: Model):
        self.name, self.described, self.model = name, described, model
        self.workspace, self.deployed = work / "workspace", work / "deployed"
        if self.workspace.exists():
            raise FileExistsError(f"{self.workspace} exists: a run starts from fresh materials")
        shutil.copytree(materials, self.workspace)
        shutil.copytree(materials, self.deployed)
        self._before: dict[str, str] = {}

    def materials_hash(self) -> str:
        return tree_hash(self.deployed)

    def edit(self, req: dict[str, Any], out: Path) -> StepResult:
        self._before = snapshot(self.workspace)
        t = time.monotonic()
        summary = converse(self.model, prompt("edit", arm=self.described), request_text(req),
                           file_tools(self.workspace), Transcript(out / "edit.jsonl"))
        changed = diff(self._before, snapshot(self.workspace))
        return StepResult(time.monotonic() - t, {"summary": summary, "diff": changed, "changed": bool(changed)})

    def check(self, req: dict[str, Any], out: Path) -> StepResult:
        after = snapshot(self.workspace)
        files = "\n\n".join(f"=== {name} ===\n{text}" for name, text in after.items())
        user = (f"{request_text(req)}\n\n--- The diff ---\n{diff(self._before, after) or '(no change)'}\n\n"
                f"--- Every file after the change ---\n{files}")
        t = time.monotonic()
        answer = converse(self.model, prompt("review", arm=self.described), user, [],
                          Transcript(out / "review.jsonl"))
        findings, error = parse_findings(answer)
        return StepResult(time.monotonic() - t, {"findings": findings, "error": error})

    def deploy(self, req: dict[str, Any], out: Path) -> StepResult:
        t = time.monotonic()
        shutil.rmtree(self.deployed)
        shutil.copytree(self.workspace, self.deployed)
        return StepResult(time.monotonic() - t, {"deployed": True, "hash": tree_hash(self.deployed)})


def nl_arm(materials: Path, work: Path, model: Model) -> TextArm:
    return TextArm("nl", "a natural-language skill for two domains (SKILL.md, with worked examples)",
                   materials, work, model)


def structured_arm(materials: Path, work: Path, model: Model) -> TextArm:
    return TextArm("structured", "the YAML declarations of two domains and the composition that joins them",
                   materials, work, model)


def render_skill(declarations: Path, out: Path, model: Model, transcript: Path) -> str:
    """The NL arm's materials, rendered from the declarations by a fresh conversation that sees
    only them (ADR-0040 §3). `out` starts as a copy of the declarations; the YAML is removed
    once SKILL.md and EXAMPLES.md are written."""
    if out.exists():
        raise FileExistsError(out)
    shutil.copytree(declarations, out)
    answer = converse(model, prompt("render"), "Write SKILL.md and EXAMPLES.md from the files in the workspace.",
                      file_tools(out), Transcript(transcript))
    missing = [f for f in ("SKILL.md", "EXAMPLES.md") if not (out / f).is_file()]
    if missing:
        raise RuntimeError(f"the rendering did not write {missing}")
    for p in list(out.rglob("*")):
        if p.is_file() and p.name not in ("SKILL.md", "EXAMPLES.md"):
            p.unlink()
    for p in sorted((x for x in out.rglob("*") if x.is_dir()), reverse=True):
        if not any(p.iterdir()):
            p.rmdir()
    return answer
