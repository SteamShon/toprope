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

It proposes each element through `toprope-run`, as whoever runs it (an agent, with its drafting
grant). Then it checks the working copy as `check_commit` would, on a scratch copy of the
domain's commit store, so the tracked store gains no commit until the person's request makes
the one that is approved (#208's review). If a check finds something it stops there and says
which, with the fix. If not, it prints the diff a person will confirm (`toprope-run review`)
and writes one human request, `.toprope/requests/<id>.yaml`, whose steps confirm, commit, check
and approve (ADR-0039). The person approves that one request, in GitHub or with `toprope-apply` at
their terminal; nothing an agent did is enforced before they do (ADR-0041).

Every step runs as its own process, as `toprope-run` does, so the identity and the kernel are
the same as by hand. Options a step needs come from toprope.yaml, as for `toprope-run`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from ...errors import MARK, fixed

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
    ap.add_argument("--kernel-root", help="where the commit store is (default: `kernel_root:` in toprope.yaml, or here)")
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


def kernel_root(given: str | None) -> Path:
    if given:
        return Path(given)
    from . import CONFIG, read_config
    if Path(CONFIG).is_file():
        return Path(read_config(Path(CONFIG)).get("kernel_root", "."))
    return Path(".")


def dry_check(root: Path, workspace: str | None) -> tuple[str, list[str], str, tuple[str, list[str]]]:
    """The change check `check_commit` runs, on a scratch copy of the domain's commit store: the
    working copy is committed there, checked against the same base, with the domain's own event
    log replayed, and the copy is thrown away. Returns (domain, what failed, summary, risk). A check
    that did not run is not a pass: no check at all is an error."""
    from ...check import check_commit
    from ...commits import CommitStore
    from ...store import open_store
    from ...workspace import Workspace
    from . import CONFIG, read_config
    ws_path = workspace or (read_config(Path(CONFIG)).get("workspace") if Path(CONFIG).is_file() else None)
    if not ws_path:
        raise SystemExit(fixed("no workspace to check", "give --workspace, or set `workspace:` in toprope.yaml"))
    ws = Workspace(ws_path)
    domain = ws.draft().get("domain")
    store_dir = root / ".toprope" / "commits" / str(domain)
    with tempfile.TemporaryDirectory() as tmp:
        if store_dir.is_dir():
            shutil.copytree(store_dir, Path(tmp) / str(domain), ignore=shutil.ignore_patterns(".lock"))
        scratch = CommitStore(Path(tmp))
        c, _ = scratch.commit(ws.domain_path, author="toprope-change")
        events_dir = ws.domain_path.parent / "events"
        events = open_store(f"jsonl:{events_dir}") if events_dir.is_dir() else None
        r = check_commit(scratch, str(domain), c.id, events=events,
                         tlc=os.environ.get("TOPROPE_TLC_JAR") or None)
        scratch_domain = scratch.domain(str(domain), c.id)
        base = r.diff.get("from")
        scratch_old = scratch.domain(str(domain), base) if base else None
        from ...check.risk import warnings_of
        base_warnings = warnings_of(scratch.check_status(str(domain), base)) if base else None
    ran = [n for n, x in r.checks.items() if x.ran]
    if not ran:
        raise SystemExit(fixed(f"no check ran on {domain}'s working copy", "check the draft with "
                               "`toprope-run check_commit` after a commit, and report the problem"))
    failing = [f"{n}: {x.summary() if hasattr(x, 'summary') else x}" for n, x in r.checks.items()
               if x.ran and not x.ok]
    from ...check.risk import assess
    # TLC runs in the request's own check (the workflow sets it); that recorded risk is what ships
    risk = assess(r, scratch_domain, scratch_old, pending=frozenset({"tla"}), base_warnings=base_warnings)
    return str(domain), failing, r.summary(), risk


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
    return f"{s or 'change'}-{uuid.uuid4().hex[:6]}"


SHIP = (("authoring", "deliver", "$commit", {"environment": "local"}),
        ("delivery", "preview", "{draft}:$commit:local", None),
        ("delivery", "deploy", "{draft}:$commit:local", None),
        ("delivery", "run_probes", "{draft}:$commit:local", None),
        ("delivery", "verify", "{draft}:$commit:local", None))


def request_for(intent: str, draft: str, member: str, workspace: str | None,
                risk: str | None = None, reasons: list[str] | None = None) -> dict[str, Any]:
    """The human request that takes the change through (ADR-0039; tools/human_request.py). A
    low-risk change also ships on the same approval, verify included, which runs only if the
    probes passed (ADR-0050); a high-risk one stops at approval, and ships on a second request
    after the person has read the preview. With `reasons`, the request carries the risk the change
    check found, which the run page shows (ADR-0050, 4)."""
    base = {"member": member, **({"workspace": workspace} if workspace else {})}
    steps = [{"run": {**base, "action": a, "target": t}} for a, t in (
        ("confirm_all_proposed", draft), ("commit_draft", draft),
        ("check_commit", "$commit"), ("approve_commit", "$commit"))]
    if risk == "low":
        for m, action, target, params in SHIP:
            steps.append({"run": {"member": m, "action": action, "target": target.format(draft=draft),
                                  **({"params": params} if params else {})}})
    head = {"low": "[low risk: one approval ships it] ", "high": "[high risk: approval only] "}.get(risk or "", "")
    out: dict[str, Any] = {"summary": head + intent, "steps": steps}
    if risk is not None and reasons is not None:
        out["risk"] = {"level": risk, "reasons": [str(r) for r in reasons]}
    return out


def pending_requests() -> list[str]:
    """Request files not yet committed: the workflow takes exactly one per push."""
    r = subprocess.run(["git", "status", "--porcelain", "--", REQUESTS], capture_output=True, text=True)
    return [line[3:] for line in r.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    items = read_patch(a.patch)
    if a.workspace and not a.workspace.endswith(".workspace.yaml"):
        raise SystemExit(fixed(f"--workspace {a.workspace} is not a workspace file",
                               "give the `*.workspace.yaml` file a human request can name"))
    if (waiting := pending_requests()):
        raise SystemExit(fixed(f"a request is already waiting to be pushed: {', '.join(waiting)}",
                               "push it (one request per push), or remove it, then run the change"))
    if a.request and Path(a.request).exists():
        raise SystemExit(fixed(f"{a.request} exists", "name a new request file, or leave --request out"))
    base = [*shlex.split(a.run_args), "--member", a.member,
            *(["--workspace", a.workspace] if a.workspace else []),
            *(["--kernel-root", a.kernel_root] if a.kernel_root else [])]
    proposed: list[str] = []
    for it in items:
        origin = it.get("origin") or a.origin
        if not origin:
            raise SystemExit(fixed(f"{it['path']} names no origin", "give it `origin:` (a Source object's id), "
                                   "or --origin for every element"))
        try:
            step(base, "propose_element", f"E-{uuid.uuid4().hex[:8]}", "--path", str(it["path"]), "--origin",
                 str(origin), "--cites", str(it["cites"]), "--value", json.dumps(it["value"]))
        except StepFailed as e:
            left = f"; already proposed and still in the draft: {', '.join(proposed)}" if proposed else ""
            # the step's message names its own fix: keep one `Fix:`, the step's first
            said, _, its_fix = str(e.code).partition(MARK)
            first = f"{its_fix.strip().rstrip('.')}; then " if its_fix else "fix that element and "
            raise SystemExit(fixed(f"{said.strip()}{left}", f"{first}run the change again with the elements not "
                                   "yet proposed, or restore the draft with `git checkout -- <declaration>`")) from None
        proposed.append(str(it["path"]))
        print(f"proposed {it['path']}", file=sys.stderr)
    domain, failing, summary, (risk, reasons) = dry_check(kernel_root(a.kernel_root), a.workspace)
    if failing:
        raise SystemExit(fixed(f"the change check found problems in {domain}'s working copy: "
                               + "; ".join(failing) + f" (proposed and still in the draft: {', '.join(proposed)})",
                               "fix the proposals and run the change again; nothing was requested"))
    review = step(base, "review")
    req = request_for(a.intent, a.draft, a.member, a.workspace, risk, list(reasons))
    path = Path(a.request) if a.request else Path(REQUESTS) / f"{slug(a.intent)}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(req, sort_keys=False, allow_unicode=True))
    print(review.get("text", "") if isinstance(review, dict) else str(review), end="")
    print(json.dumps({"proposed": proposed, "checked": summary, "risk": risk, "risk_reasons": reasons,
                      "request": str(path),
                      **({"then": f"high risk: in GitHub, after this request is approved, read the preview, "
                                  f"then write the delivery request with `python tools/human_request.py ship "
                                  f"<request> --commit <the approved commit> --domain {domain}`; at a terminal, "
                                  f"`toprope-apply --ship {path}` approves it and stops after the preview, and "
                                  f"`toprope-apply {path}` again ships it once the person has read it"}
                         if risk != "low" else {}),
                      "next": "a person takes the request by one of two routes, and that one approval "
                              "confirms, commits, checks and approves: (a) commit the request with the draft "
                              "and the event logs it changed and push them, and the person approves its run "
                              f"in GitHub; or (b) the person runs `toprope-apply {path}` on their own "
                              "terminal and types `yes`, then commits the result (one loop at a time: "
                              "AGENTS.md)"},
                     indent=2))


__all__ = ["build_parser", "dry_check", "main", "read_patch", "request_for"]
