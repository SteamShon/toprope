"""Run a human request: steps only the researcher may take, approved in GitHub (ADR-0039).

A request is a file `.toprope/requests/<id>.yaml` on a work branch:

    summary: Freeze the M1 binding
    steps:
      - freeze-binding: experiments/m1/instruments
      - run: {member: authoring, action: check_commit, target: 5-ab12cd34ef56ab78}
      - run: {member: authoring, action: approve_commit, target: 5-ab12cd34ef56ab78}
      - run: {member: authoring, action: confirm_all_proposed, target: authoring}

Steps, from a fixed set:
- `freeze: DIR`, `freeze-binding: DIR`, `freeze-protocol: DIR`: `experiments/tools/instruments.py`
- `amend: {dir: DIR, file: FILE, reason: TEXT}`: the same, on the record
- `run: {member, action, target, params, workspace}`: a self-domain action through `toprope-run`, as
  the approver (`--identity github`). `workspace` defaults to `toprope.<member>.workspace.yaml`;
  an Authoring action on the Delivery declaration's draft names `toprope.delivery.workspace.yaml`.
  An `approve_commit` step needs a `check_commit` step on the same commit before it: the
  workflow sets `TOPROPE_TLC_JAR`, so that check model-checks with TLC, and the kernel approves
  only a commit whose TLC check passed (ADR-0043)
- `target: $commit`: the commit the request's last `commit_draft` step before it made, also
  inside a target (`delivery:$commit:local`, the delivery request of that commit). So one
  request takes a change from proposed to approved, and on to verified: `change` writes the
  first part.

  python tools/human_request.py change REQUEST --draft DRAFT [--member authoring] [--workspace W]

writes REQUEST with the four steps: confirm_all_proposed, commit_draft, check_commit $commit,
approve_commit $commit.

`.github/workflows/human-request.yml` calls `check` (and shows `render` on the run page) before
it waits for the approval, and `run` after it.

  python tools/human_request.py check REQUEST
  python tools/human_request.py render REQUEST
  python tools/human_request.py run REQUEST --approver LOGIN [--identity toprope.identity.yaml]
  python tools/human_request.py record REQUEST --approver LOGIN --as PERSON --run-url URL

`record` appends the approved run to `.toprope/approval-runs.jsonl`, committed with the result,
so a commit can cite the run as evidence (`cite_evidence --kind approval-run`) after any merge.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = ".toprope/requests"
APPROVAL_RUNS = ".toprope/approval-runs.jsonl"
INSTRUMENT_STEPS = ("freeze", "freeze-binding", "freeze-protocol", "amend")
COMPOSITION = "domains/toprope-self.composition.yaml"
MADE = "$commit"                     # the commit an earlier commit_draft step of the request made
TLC_ENV = "TOPROPE_TLC_JAR"         # the kernel model-checks with it; approval needs it (ADR-0043)


def load(path: str | Path) -> dict:
    req = yaml.safe_load(Path(path).read_text())
    errors = check(req)
    if errors:
        raise ValueError("; ".join(errors))
    return req


def check(req: object) -> list[str]:
    """Errors in a request; empty means it may be shown for approval."""
    if not isinstance(req, dict) or set(req) - {"summary", "steps"}:
        return ["a request has `summary` and `steps`, nothing else"]
    errors = []
    if not isinstance(req.get("summary"), str) or not req["summary"].strip():
        errors.append("summary: say in one line what you approve")
    steps = req.get("steps")
    if not isinstance(steps, list) or not steps:
        return errors + ["steps: a non-empty list"]
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict) or len(st) != 1:
            errors.append(f"step {i}: one of {', '.join(INSTRUMENT_STEPS)} or run")
            continue
        (kind, arg), = st.items()
        if kind in ("freeze", "freeze-binding", "freeze-protocol"):
            if not isinstance(arg, str) or not arg:
                errors.append(f"step {i}: {kind} takes the instruments directory")
        elif kind == "amend":
            if not isinstance(arg, dict) or set(arg) != {"dir", "file", "reason"} \
                    or not all(isinstance(v, str) and v.strip() for v in arg.values()):
                errors.append(f"step {i}: amend takes dir, file and reason")
        elif kind == "run":
            if not isinstance(arg, dict) or not {"member", "action", "target"} <= set(arg) \
                    or set(arg) - {"member", "action", "target", "params", "workspace"} \
                    or not isinstance(arg.get("workspace", "x.workspace.yaml"), str) \
                    or not str(arg.get("workspace", "x.workspace.yaml")).endswith(".workspace.yaml") \
                    or not all(isinstance(arg[k], str) and arg[k] for k in ("member", "action", "target")) \
                    or not isinstance(arg.get("params", {}), dict):
                errors.append(f"step {i}: run takes member, action, target, and optional params and workspace "
                              "(a *.workspace.yaml)")
        else:
            errors.append(f"step {i}: {kind!r} is not a step (one of {', '.join(INSTRUMENT_STEPS)} or run)")
    checked, drafted = set(), False
    for i, st in enumerate(steps, 1):        # TLC runs only in the workflow: check where you approve
        arg = st.get("run") if isinstance(st, dict) else None
        if not isinstance(arg, dict):
            continue
        key = (arg.get("member"), arg.get("target"))
        if MADE in str(arg.get("target")) and not drafted:
            errors.append(f"step {i}: {MADE} names the commit a commit_draft step before it makes; there is none")
        if arg.get("action") == "commit_draft":
            drafted = True
            checked.discard((arg.get("member"), MADE))   # a new commit: check it again
        if arg.get("action") == "check_commit":
            checked.add(key)
        elif arg.get("action") == "approve_commit" and key not in checked:
            errors.append(f"step {i}: approve_commit {arg.get('target')} needs a check_commit step on it before, "
                          "in this request: approval needs the TLC check, which runs only here (ADR-0043)")
    return errors


def render(req: dict) -> str:
    """What the researcher reads on the run page before approving."""
    lines = [f"### Human request: {req['summary']}", "",
             "Approving runs these steps as you, in this order:", ""]
    for i, st in enumerate(req["steps"], 1):
        (kind, arg), = st.items()
        if kind == "run":
            params = " ".join(f"--{k.replace('_', '-')} {json.dumps(v) if not isinstance(v, str) else v}"
                              for k, v in (arg.get("params") or {}).items())
            where = f" (workspace `{arg['workspace']}`)" if arg.get("workspace") else ""
            target = "the commit made above" if arg["target"] == MADE else \
                f"`{arg['target']}`".replace(MADE, "<the commit made above>")
            lines.append(f"{i}. `{arg['member']}`: **{arg['action']}** {target} {params}".rstrip() + where)
        elif kind == "amend":
            lines.append(f"{i}. **amend** `{arg['file']}` in `{arg['dir']}`: {arg['reason']}")
        else:
            lines.append(f"{i}. **{kind}** `{arg}`")
    for st in req["steps"]:                      # what a confirm step confirms, as one diff (B5)
        (kind, arg), = st.items()
        if kind == "run" and arg.get("action") in ("confirm_all_proposed", "confirm_element"):
            lines += ["", f"#### What `{arg['action']}` confirms", "", "```diff",
                      review(arg.get("workspace") or f"toprope.{arg['member']}.workspace.yaml").rstrip(), "```"]
    return "\n".join(lines) + "\n"


def review(workspace: str, cwd: str | Path = ".") -> str:
    """The proposed elements a confirm step would confirm, against the domain's `main`."""
    sys.path.insert(0, str(ROOT / "src"))
    from toprope.workspace import Workspace
    try:
        return Workspace(Path(cwd) / workspace).render_review()
    except Exception as e:                       # noqa: BLE001 - the page still shows the steps
        return f"(the review could not be made: {e})"


def commands(req: dict) -> list[list[str]]:
    """The command for each step (`$commit` as written: `run` puts the commit in)."""
    return [command(st) for st in req["steps"]]


def command(st: dict, made: str | None = None) -> list[str]:
    tool = [sys.executable, str(ROOT / "experiments/tools/instruments.py")]
    (kind, arg), = st.items()
    if kind in ("freeze", "freeze-binding", "freeze-protocol"):
        return tool + [kind, arg]
    if kind == "amend":
        return tool + ["amend", arg["dir"], arg["file"], "--reason", arg["reason"]]
    target = arg["target"].replace(MADE, made) if made else arg["target"]
    cmd = ["toprope-run", "--composition", COMPOSITION, "--member", arg["member"],
           "--kernel-root", ".", "--workspace", arg.get("workspace") or f"toprope.{arg['member']}.workspace.yaml",
           "--env", ".toprope/env", "--identity", "github", arg["action"], target]
    for k, v in (arg.get("params") or {}).items():
        cmd += [f"--{k.replace('_', '-')}", v if isinstance(v, str) else json.dumps(v)]
    return cmd


def change(draft: str, member: str = "authoring", workspace: str | None = None, summary: str | None = None) -> dict:
    """One change, one request: confirm what is proposed, commit, check, approve."""
    base = {"member": member, **({"workspace": workspace} if workspace else {})}
    return {"summary": summary or f"Confirm, commit, check and approve the change in draft {draft}",
            "steps": [{"run": {**base, "action": a, "target": t}} for a, t in (
                ("confirm_all_proposed", draft), ("commit_draft", draft),
                ("check_commit", MADE), ("approve_commit", MADE))]}


def _made(stdout: str) -> str | None:
    """The commit a commit_draft step made: its `commit` kernel call's object."""
    try:
        then = (json.loads(stdout) or {}).get("then") or []
    except (ValueError, AttributeError):
        return None
    return next((t.get("object") for t in then if t.get("kernel") == "commit" and t.get("status") == "ok"), None)


def _unmet(stdout: str) -> list[str]:
    """What an accepted action set off and did not get done: a kernel call that failed or was
    refused (an approval without TLC's check, ADR-0044), or a handoff that did not go through.
    The action itself was accepted, so `toprope-run` exits 0; the request has still failed."""
    try:
        then = (json.loads(stdout) or {}).get("then") or []
    except (ValueError, AttributeError):
        return []
    return [f"{t.get('kernel') or t.get('to')}: {t.get('status')}" + (f" ({t['error']})" if t.get("error") else "")
            for t in then if t.get("status") != "ok"]


def run(req: dict, approver: str, identity: str = "toprope.identity.yaml", cwd: str | Path = ".") -> list[dict]:
    """Run every step as the approver; stop at the first that fails."""
    sys.path.insert(0, str(ROOT / "src"))
    from toprope.identity.github import ENV, github_logins
    person = github_logins(Path(cwd) / identity).get(approver.lower())
    if person is None:
        raise SystemExit(f"GitHub user {approver} approved, but is not a person with `github:` in {identity}")
    env = {**os.environ, ENV: approver}
    if any((st.get("run") or {}).get("action") == "approve_commit" for st in req["steps"]) \
            and not env.get(TLC_ENV):
        raise SystemExit(f"approve_commit needs TLC: set {TLC_ENV} to a TLC jar (the workflow does)")
    done, made = [], None
    for st in req["steps"]:
        arg = st.get("run") or {}
        if MADE in str(arg.get("target")) and made is None:
            raise SystemExit(f"step {len(done) + 1}: {MADE}, but no commit_draft step before it made a commit")
        cmd = command(st, made)
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
        done.append({"step": st, "returncode": r.returncode, "stdout": r.stdout[-4000:], "stderr": r.stderr[-4000:]})
        unmet = _unmet(r.stdout) if r.returncode == 0 and "run" in st else []
        if r.returncode != 0 or unmet:
            print(json.dumps(done, indent=2), file=sys.stderr)
            why = "; ".join(unmet) or r.stderr[-2000:]
            raise SystemExit(f"step {len(done)} failed: {' '.join(cmd[:6])} ...\n{why}")
        if arg.get("action") == "commit_draft" and (c := _made(r.stdout)):
            made = c
            done[-1]["commit"] = c
    print(json.dumps({"approver": approver, "as": person.actor.id, "steps": len(done),
                      **({"commit": made} if made else {})}, indent=2))
    return done


def record(req: dict, approver: str, person: str, run_url: str, cwd: str | Path = ".") -> dict:
    """Append the approved run, its approver and its steps to the approval-run log."""
    from datetime import datetime, timezone
    entry = {"run": run_url, "approver": approver, "as": person, "summary": req["summary"],
             "steps": req["steps"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path = Path(cwd) / APPROVAL_RUNS
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "render", "run", "record", "change"])
    ap.add_argument("request")
    ap.add_argument("--approver", help="the GitHub login that approved the run (for run)")
    ap.add_argument("--identity", default="toprope.identity.yaml")
    ap.add_argument("--as", dest="person", help="the person the approver acted as (for record)")
    ap.add_argument("--run-url", help="the approved workflow run (for record)")
    ap.add_argument("--draft", help="the draft whose change to take through (for change)")
    ap.add_argument("--member", default="authoring", help="(for change)")
    ap.add_argument("--workspace", help="(for change) the draft's workspace, if not the member's")
    ap.add_argument("--summary", help="(for change)")
    args = ap.parse_args(argv)
    if args.cmd == "change":
        if not args.draft:
            raise SystemExit("change needs --draft")
        req = change(args.draft, args.member, args.workspace, args.summary)
        Path(args.request).parent.mkdir(parents=True, exist_ok=True)
        Path(args.request).write_text(yaml.safe_dump(req, sort_keys=False, allow_unicode=True))
        print(args.request)
        return
    try:
        req = load(args.request)
    except (OSError, ValueError, yaml.YAMLError) as e:
        raise SystemExit(f"{args.request}: {e}") from None
    if args.cmd == "check":
        print("ok")
    elif args.cmd == "render":
        print(render(req), end="")
    elif args.cmd == "record":
        if not (args.approver and args.person and args.run_url):
            raise SystemExit("record needs --approver, --as and --run-url")
        record(req, args.approver, args.person, args.run_url)
    else:
        if not args.approver:
            raise SystemExit("run needs --approver")
        run(req, args.approver, args.identity)


if __name__ == "__main__":
    main()
