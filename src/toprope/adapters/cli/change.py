"""`toprope-change`: one command takes a change from an agent's proposals to one request for a
person (ADR-0049, C1).

    toprope-change "Drafts name their declaration" --patch change.yaml [--draft authoring]

`change.yaml` lists the elements the change proposes, each with what it cites (a chunk ref, or
words from the passage):

    - path: invariants.drafts-name-their-declaration
      value: {id: drafts-name-their-declaration, on: Draft, check: "exists(target.declaration)",
              reason: A draft is the working copy of one declaration.}
      cites: "interview: The working copy of a declaration."
      origin: S-adr                      # the Source object it came from (default: --origin)

It runs, through `toprope-run` and as whoever runs it (an agent, with its drafting grant):
`propose_element` for each element, `commit_draft`, and `check_commit` on that commit. If a
check fails it stops there and says which, with the fix. If they pass it prints the diff a
person will confirm (`toprope-run review`) and writes one human request,
`.toprope/requests/<id>.yaml`, whose steps confirm, commit, check and approve (ADR-0039). The
person approves that one request; nothing an agent did is enforced before they do (ADR-0041).

Every step runs as its own process, as `toprope-run` does, so the identity and the kernel are
the same as by hand. Options a step needs come from toprope.yaml, as for `toprope-run`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from ...errors import fixed

REQUESTS = ".toprope/requests"
RUN = [sys.executable, "-c", "from toprope.adapters.cli import main; main()"]


class StepFailed(SystemExit):
    pass


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-change", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("intent", help="what the change is for, in a sentence; the request's summary")
    ap.add_argument("--patch", required=True, help="a YAML list of {path, value, cites, origin}")
    ap.add_argument("--draft", default="authoring", help="the draft the change is made in (default: authoring)")
    ap.add_argument("--member", default="authoring", help="the member whose actions these are")
    ap.add_argument("--origin", help="the Source object an element came from, when it names none")
    ap.add_argument("--workspace", help="the draft's workspace, if not the one in toprope.yaml")
    ap.add_argument("--kernel-root", default=".", help="where the commit store is (default: here)")
    ap.add_argument("--request", help=f"the request file to write (default: {REQUESTS}/<id>.yaml)")
    ap.add_argument("--run-args", default="", help="options passed to every toprope-run step, "
                    "e.g. \"--identity static:ids.yaml\"")
    return ap


def read_patch(path: str | Path) -> list[dict[str, Any]]:
    try:
        items = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as e:
        raise SystemExit(fixed(f"cannot read the patch {path}: {e}", "give a YAML list of elements")) from None
    if not isinstance(items, list) or not items:
        raise SystemExit(fixed(f"the patch {path} lists no elements",
                               "write a YAML list of `{path, value, cites}`, one per element"))
    for i, it in enumerate(items, 1):
        missing = [k for k in ("path", "value", "cites") if not isinstance(it, dict) or k not in it]
        if missing:
            raise SystemExit(fixed(f"element {i} of the patch has no {', '.join(missing)}",
                                   "give each element its `path`, `value` and `cites`"))
    return items


def step(base: list[str], *args: str) -> dict[str, Any]:
    """One `toprope-run` command, as its own process. A failure stops the change, with the
    command's own message (which names its fix)."""
    r = subprocess.run([*RUN, *base, *args], capture_output=True, text=True)
    out: dict[str, Any] = {}
    if r.stdout.strip():
        try:
            out = json.loads(r.stdout)
        except ValueError:
            out = {"text": r.stdout}
    if r.returncode != 0:
        why = r.stderr.strip() or out.get("reason") or r.stdout.strip()
        raise StepFailed(f"{args[0]} {args[1] if len(args) > 1 else ''} failed: {why}".strip())
    failed = [t for t in out.get("then", []) if t.get("status") not in ("ok", None) or t.get("error")]
    if failed:
        raise StepFailed(f"{args[0]} {args[1]}: what it set off failed: "
                         + "; ".join(str(t.get("error") or t.get("reason")) for t in failed))
    return out


def failing_checks(kernel_root: Path, domain: str, commit: str) -> list[str]:
    """The checks that found something. `confirmed` is not one: it fails until a person confirms
    the proposals, which is what the request is for; a skipped check did not run."""
    from ...commits import CommitStore
    rows = CommitStore(kernel_root / ".toprope" / "commits").check_status(domain, commit)
    return [f"{name}: {r.get('summary')}" for name, r in rows.items()
            if not r.get("ok") and name != "confirmed" and not str(r.get("summary", "")).startswith("skipped")]


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
    return f"{s or 'change'}-{uuid.uuid4().hex[:6]}"


def request_for(intent: str, draft: str, member: str, workspace: str | None) -> dict[str, Any]:
    """The human request that takes the change through (ADR-0039; tools/human_request.py)."""
    base = {"member": member, **({"workspace": workspace} if workspace else {})}
    return {"summary": intent,
            "steps": [{"run": {**base, "action": a, "target": t}} for a, t in (
                ("confirm_all_proposed", draft), ("commit_draft", draft),
                ("check_commit", "$commit"), ("approve_commit", "$commit"))]}


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    items = read_patch(a.patch)
    base = [*a.run_args.split(), "--member", a.member, *(["--workspace", a.workspace] if a.workspace else [])]
    for it in items:
        origin = it.get("origin") or a.origin
        if not origin:
            raise SystemExit(fixed(f"{it['path']} names no origin", "give it `origin:` (a Source object's id), "
                                   "or --origin for every element"))
        step(base, "propose_element", f"E-{uuid.uuid4().hex[:8]}", "--path", str(it["path"]), "--origin",
             str(origin), "--cites", str(it["cites"]), "--value", json.dumps(it["value"]))
        print(f"proposed {it['path']}", file=sys.stderr)
    made = step(base, "commit_draft", a.draft)
    commits = [t["object"] for t in made.get("then", []) if t.get("object")]
    if not commits:
        raise SystemExit(fixed("commit_draft made no commit", "check that the draft has changes to commit"))
    commit = commits[-1]
    step(base, "check_commit", commit)
    state = step(base, "get", commit)
    failed = failing_checks(Path(a.kernel_root), state.get("domain_id") or a.draft, commit)
    if failed:
        raise SystemExit(fixed(f"{commit}'s checks found problems: " + "; ".join(failed),
                               f"see `toprope-commits checks {state.get('domain_id') or a.draft} {commit}`, "
                               "fix the proposals and run the change again"))
    review = step(base, "review").get("text", "")
    req = request_for(a.intent, a.draft, a.member, a.workspace)
    path = Path(a.request) if a.request else Path(REQUESTS) / f"{slug(a.intent)}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(req, sort_keys=False, allow_unicode=True))
    print(review, end="")
    print(json.dumps({"proposed": [it["path"] for it in items], "checked": commit, "request": str(path),
                      "next": "commit and push the branch with the request; the person approves it in "
                              "GitHub, and that one approval confirms, commits, checks and approves"},
                     indent=2))


__all__ = ["build_parser", "main", "read_patch", "request_for"]
