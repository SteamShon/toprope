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

from .agent import Transcript
from .backend import Backend
from .toolserver import ToolSpec

PROMPTS = Path(__file__).parent / "prompts"


def prompt(name: str, **fill: str) -> str:
    """A role's prompt. The harness's own text in it (the template, and every fill but the
    domain's materials) is checked for experiment words (run protocol §1)."""
    from .blind import check
    text = (PROMPTS / f"{name}.md").read_text()
    for k, v in fill.items():
        if k != "materials":
            text = text.replace("{" + k + "}", v)
    if not name.startswith("grade_"):              # the grader sees the key; it is not in an arm
        check(f"prompt {name}", text)
    return text.replace("{materials}", fill.get("materials", "{materials}"))


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
    """A change request as the agents get it: the frozen intent and rationale, nothing else."""
    return f"Change request {req['seq']}: {req['intent']}\nWhy: {req.get('rationale', '').strip()}"


def parse_findings(text: str) -> tuple[list[dict[str, Any]], str | None]:
    """The reviewer's findings: the first JSON object in its answer with a `findings` list, and
    an error when there is none."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            data, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("findings"), list):
            return [f for f in data["findings"] if isinstance(f, dict)], None
    return [], "the review did not answer with the JSON asked for"


@dataclass
class StepResult:
    seconds: float
    data: dict[str, Any] = field(default_factory=dict)


class TextArm:
    """An arm whose domain is a set of text files, checked by an LLM review.

    A new run copies the materials. Resuming one (`resume=True`) starts again from what was last
    deployed: an edit left half done when the run stopped is thrown away, and that change runs
    again from the start."""

    def __init__(self, name: str, described: str, materials: Path, work: Path, backend: Backend,
                 resume: bool = False):
        self.name, self.described, self.backend = name, described, backend
        self.workspace, self.deployed = work / "workspace", work / "deployed"
        self.materials = tree_hash(materials)
        if resume:
            _recover(self.deployed)
            if not self.deployed.is_dir():
                raise FileNotFoundError(f"nothing to resume in {work}")
            shutil.rmtree(self.workspace, ignore_errors=True)
            shutil.copytree(self.deployed, self.workspace)
        else:
            if self.workspace.exists() or self.deployed.exists():
                raise FileExistsError(f"{work} has a run: resume it, or start a new run directory")
            shutil.copytree(materials, self.workspace)
            shutil.copytree(materials, self.deployed)
        self._before: dict[str, str] = {}

    def materials_hash(self) -> str:
        return self.materials

    def edit(self, req: dict[str, Any], out: Path) -> StepResult:
        self._before = snapshot(self.workspace)
        t = time.monotonic()
        summary = self.backend.converse(prompt("edit", arm=self.described), request_text(req),
                                        ToolSpec("files", str(self.workspace)), Transcript(out / "edit.jsonl"))
        changed = diff(self._before, snapshot(self.workspace))
        return StepResult(time.monotonic() - t, {"summary": summary, "diff": changed, "changed": bool(changed)})

    def check(self, req: dict[str, Any], out: Path) -> StepResult:
        after = snapshot(self.workspace)
        files = "\n\n".join(f"=== {name} ===\n{text}" for name, text in after.items())
        user = (f"{request_text(req)}\n\n--- The diff ---\n{diff(self._before, after) or '(no change)'}\n\n"
                f"--- Every file after the change ---\n{files}")
        t = time.monotonic()
        answer = self.backend.converse(prompt("review", arm=self.described), user, None,
                                       Transcript(out / "review.jsonl"))
        findings, error = parse_findings(answer)
        return StepResult(time.monotonic() - t, {"findings": findings, "error": error})

    def deploy(self, req: dict[str, Any], out: Path) -> StepResult:
        t = time.monotonic()
        _replace(self.deployed, self.workspace)
        return StepResult(time.monotonic() - t, {"deployed": True, "hash": tree_hash(self.deployed)})

    def probe(self, req: dict[str, Any], out: Path, worlds: Path, probes: list[dict[str, Any]],
              jobs: int = 1) -> list[dict[str, Any]]:
        """The probes after this change, with the deployed text as the rules to follow."""
        from .probes import run_probes
        materials = "\n\n".join(f"=== {name} ===\n{text}" for name, text in snapshot(self.deployed).items())
        return run_probes(self.backend, worlds, probes, out / "probes", self.described, materials, jobs=jobs)


def _replace(target: Path, source: Path) -> None:
    """Make `target` a copy of `source` so that a stop at any point leaves either the old copy or
    the new one (`_recover` finishes the job on resume)."""
    new, old = target.with_name(target.name + ".new"), target.with_name(target.name + ".old")
    shutil.rmtree(new, ignore_errors=True)
    shutil.copytree(source, new)
    shutil.rmtree(old, ignore_errors=True)
    target.rename(old)
    new.rename(target)
    shutil.rmtree(old)


def _recover(target: Path) -> None:
    new, old = target.with_name(target.name + ".new"), target.with_name(target.name + ".old")
    if not target.exists() and new.is_dir() and old.is_dir():
        new.rename(target)                      # stopped between the two renames: the copy was complete
    elif not target.exists() and old.is_dir():
        old.rename(target)
    shutil.rmtree(new, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)


def nl_arm(materials: Path, work: Path, backend: Backend, resume: bool = False) -> TextArm:
    return TextArm("nl", "a natural-language skill for two domains (SKILL.md, with worked examples)",
                   materials, work, backend, resume)


def structured_arm(materials: Path, work: Path, backend: Backend, resume: bool = False) -> TextArm:
    return TextArm("structured", "the YAML declarations of two domains and the composition that joins them",
                   materials, work, backend, resume)


def render_skill(declarations: Path, out: Path, backend: Backend, transcript: Path) -> str:
    """The NL arm's materials, rendered from the declarations by a fresh conversation that sees
    only them (ADR-0040 §3). `out` starts as a copy of the declarations; the YAML is removed
    once SKILL.md and EXAMPLES.md are written."""
    if out.exists():
        raise FileExistsError(out)
    shutil.copytree(declarations, out)
    answer = backend.converse(prompt("render"), "Write SKILL.md and EXAMPLES.md from the files in the workspace.",
                              ToolSpec("files", str(out)), Transcript(transcript))
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
