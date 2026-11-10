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
  python tools/human_request.py ship REQUEST --commit COMMIT [--domain authoring]   (ADR-0050: the
      second request of a high-risk change, after its preview was read)

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

A step that fails stops the run, and the work of the steps before it is kept: `run` prints how
far it got and exits non-zero, `record --done` notes the failed step in the run's entry and
rewrites the request to the steps that are left, and the workflow commits and pushes that, then
ends red. So a failed preview leaves the commit approved, as ADR-0050 says. What the failed step
half wrote is undone first; a step whose action was taken but whose follow-up failed counts as run.
To go on, fix the cause and push a change to the request (the rest): its run takes only the steps
that did not run, numbered as in the first request. Never re-run a red run: the workflow refuses
it once the branch has moved on.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
    approves = {str((st.get("run") or {}).get("target")) for st in req["steps"]
                if (st.get("run") or {}).get("action") == "approve_commit"}
    if any((st.get("run") or {}).get("action") in SHIPS
           and shipped_commit(st["run"], None) in approves for st in req["steps"]):
        lines += ["", "**One approval ships this change** (ADR-0050): the delivery steps run only if the "
                  "check in this request finds it low risk, and `verify` runs only if the probes passed; "
                  "approving verifies in advance on that condition."]
    for st in req["steps"]:                      # what a confirm step confirms, as one diff (B5)
        (kind, arg), = st.items()
        if kind == "run" and arg.get("action") in ("confirm_all_proposed", "confirm_element"):
            lines += ["", f"#### What `{arg['action']}` confirms", "", "```diff",
                      review(arg.get("workspace") or f"toprope.{arg['member']}.workspace.yaml").rstrip(), "```"]
    return "\n".join(lines) + "\n"


def review(workspace: str, cwd: str | Path = ".") -> str:
    """The proposed elements a confirm step would confirm, against the domain's `main`."""
    sys.path.insert(0, str(ROOT / "src"))
    try:                                         # the page shows the steps even if this cannot run
        from toprope.workspace import Workspace
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


SHIPS = ("deliver", "preview", "deploy", "run_probes", "verify")


def shipped_commit(arg: dict, made: str | None) -> str | None:
    """The commit a delivery step ships: `deliver <commit>`, or `<domain>:<commit>:<env>`."""
    target = str(arg.get("target", "")).replace(MADE, made or MADE)
    return target if arg.get("action") == "deliver" else (target.split(":")[1] if target.count(":") == 2 else None)


def ship(commit: str, domain: str, summary: str | None = None) -> dict:
    """The second request of a high-risk change (ADR-0050): ship an approved commit, after the
    person has read its preview."""
    t = f"{domain}:{commit}:local"
    return {"summary": summary or f"Ship {commit}, approved earlier, after reading its preview",
            "steps": [{"run": {"member": "authoring", "action": "deliver", "target": commit,
                               "params": {"environment": "local"}}},
                      *({"run": {"member": "delivery", "action": a, "target": t}}
                        for a in ("preview", "deploy", "run_probes", "verify"))]}


def recorded_risk(commit: str, cwd: str | Path = ".") -> str | None:
    """The risk `check_commit` last recorded on a commit (ADR-0050), from any domain's checks."""
    level = None
    for path in sorted((Path(cwd) / ".toprope" / "commits").glob("*/checks.jsonl")):
        for line in path.read_text().splitlines():
            row = json.loads(line) if line.strip() else {}
            if row.get("commit") == commit and row.get("check") == "risk":
                level = str(row.get("summary", "")).split(":", 1)[0].strip()
    return level


REST = re.compile(r" \(the rest: steps? ([0-9, -]+) of (\d+)\)$")


def _spans(nums: list[int]) -> str:
    """`step 5`, `steps 1-4`, `steps 3, 5-9`."""
    parts, start = [], None
    for k, n in enumerate(nums):
        start = n if start is None else start
        if k + 1 == len(nums) or nums[k + 1] != n + 1:
            parts.append(str(n) if start == n else f"{start}-{n}")
            start = None
    return ("step " if len(nums) == 1 else "steps ") + ", ".join(parts)


def numbering(req: dict) -> tuple[str, list[int], int]:
    """The request's summary without its numbering, each step's number in the request it came
    from, and that request's length. A rest keeps the numbers of the request it is the rest of."""
    n = len(req["steps"])
    if m := REST.search(req["summary"]):
        nums = []
        for part in m.group(1).split(","):
            lo, _, hi = part.strip().partition("-")
            nums += range(int(lo), int(hi or lo) + 1)
        if len(nums) == n:
            return req["summary"][:m.start()], nums, int(m.group(2))
    return req["summary"], list(range(1, n + 1)), n


def rest(req: dict, start: int, made: str | None) -> dict | None:
    """The request that is left from step `start` (1-based) on, or None if nothing is left, with
    `$commit` put in where a commit_draft step that already ran made it. A step that ran is not in
    it, so running it does not take a step twice (`toprope-run` gives each command a new
    idempotency key, so a step run again is a new command). An `approve_commit` keeps the
    `check_commit` before it, since approval needs TLC's check in the same run (ADR-0043). Its
    summary keeps the numbers the steps had in the first request."""
    if start > len(req["steps"]):
        return None
    base, nums, total = numbering(req)
    steps, numbers, checked, own_commit = [], [], set(), False
    before = [(k, st["run"]) for k, st in enumerate(req["steps"][:start - 1]) if "run" in st]
    for k, st in enumerate(req["steps"][start - 1:], start - 1):
        (kind, arg), = st.items()
        if kind == "run":
            arg = dict(arg)
            if arg["action"] == "commit_draft":
                own_commit = True               # from here on, $commit is the commit this one makes
            if made and not own_commit:
                arg["target"] = arg["target"].replace(MADE, made)
            key = (arg["member"], arg["target"])
            if arg["action"] == "check_commit":
                checked.add(key)
            elif arg["action"] == "approve_commit" and key not in checked:
                steps.append({"run": {**{x: v for x, v in arg.items() if x != "params"}, "action": "check_commit"}})
                numbers.append(next((nums[j] for j, a in reversed(before) if a["action"] == "check_commit"
                                     and a["member"] == arg["member"]
                                     and a["target"].replace(MADE, made or MADE) == arg["target"]), nums[k]))
                checked.add(key)
            st = {"run": arg}
        steps.append(st)
        numbers.append(nums[k])
    return {"summary": f"{base} (the rest: {_spans(numbers)} of {total})", "steps": steps}


def _git(cwd: str | Path, *args: str) -> tuple[int, str]:
    # Popen, not subprocess.run: the steps' runner is replaced in the tests, git is not
    p = subprocess.Popen(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = p.communicate()
    return p.returncode, out.strip()


def snapshot(cwd: str | Path) -> str | None:
    """The working tree as a git tree (it stages everything), or None outside a git work tree."""
    if _git(cwd, "rev-parse", "--is-inside-work-tree")[0] or _git(cwd, "add", "-A")[0]:
        return None
    code, tree = _git(cwd, "write-tree")
    return tree if code == 0 else None


# What a failed step wrote as a record of its attempt, which F1 counts (tools/usability_baseline.py):
# a failure before the gate (D1b), and a refused or denied command's outcome and attempt. Kept as
# they are when the rest of the tree is put back: the attempt happened.
ATTEMPT_RECORDS = (".toprope/failures/**/*", "domains/*/events/idempotency.jsonl", "domains/*/events/attempts.jsonl")


def restore(cwd: str | Path, tree: str | None) -> None:
    """Put the working tree back to `tree`, so what a failed step half wrote is not pushed, but
    keep the records of its attempt (`ATTEMPT_RECORDS`)."""
    if tree:
        keep = {f: f.read_bytes() for pattern in ATTEMPT_RECORDS for f in Path(cwd).glob(pattern) if f.is_file()}
        _git(cwd, "add", "-A")
        _git(cwd, "read-tree", "-u", "--reset", tree)
        for f, data in keep.items():
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)


def run(req: dict, approver: str, identity: str = "toprope.identity.yaml", cwd: str | Path = ".") -> list[dict]:
    """Run every step as the approver; stop at the first that fails.

    It prints what happened as JSON on stdout, also when a step fails: `as`, `steps` (how many
    ran: the first `steps` of this request), `of`, `commit`, and on failure `failed` (`step`: its
    position in this request; `number`: its number in the first request, as `label` gives it; why;
    and `accepted` when its action was taken but what it set off failed, so it is one of the
    `steps` that ran), `label` (what happened, in the first
    request's step numbers) and `rest` (the request that is left, see `rest`; null if none). Then
    a failure exits non-zero, after the work of the steps before it is on disk, so the workflow
    commits that work (ADR-0050, 2: the commit stays approved) and the run still ends red.

    A step that failed is undone in the working tree (it is restored to the snapshot taken after
    the last step that ran, in a git work tree), so only the work of the steps that ran is pushed,
    and the step is in the rest. A step whose action was taken, but whose follow-up (a kernel call
    or a handoff) failed, has run: its work is kept and the rest starts after it, so it is not sent
    twice. A failure before any step ran (no such person, no TLC) prints nothing."""
    sys.path.insert(0, str(ROOT / "src"))
    from toprope.errors import fixed
    from toprope.identity.github import ENV, github_logins
    person = github_logins(Path(cwd) / identity).get(approver.lower())
    if person is None:
        raise SystemExit(f"GitHub user {approver} approved, but is not a person with `github:` in {identity}")
    env = {**os.environ, ENV: approver}
    if any((st.get("run") or {}).get("action") == "approve_commit" for st in req["steps"]) \
            and not env.get(TLC_ENV):
        raise SystemExit(f"approve_commit needs TLC: set {TLC_ENV} to a TLC jar (the workflow does)")
    _, nums, total = numbering(req)
    done, made, approved = [], None, set()
    tree = snapshot(cwd)
    again = "fix the cause, then push a change to the request (the workflow leaves the steps that did not run " \
            "in it), and approve that run; do not re-run this run"

    def report(**more) -> None:
        print(json.dumps({"approver": approver, "as": person.actor.id, "steps": len(done), "of": len(req["steps"]),
                          **({"commit": made} if made else {}), **more}, indent=2))

    def stop(i: int, message: str, fix: str, attempt: dict | None = None, accepted: bool = False) -> None:
        print(json.dumps(done + ([attempt] if attempt and not accepted else []), indent=2), file=sys.stderr)
        if not accepted:
            restore(cwd, tree)
        what = f"step {nums[i - 1]} of {total} " + ("was taken, but what it set off failed" if accepted else "failed")
        ran = nums[:len(done)]
        if ran:
            what += f"; {_spans(ran)} ran and {'its' if len(ran) == 1 else 'their'} work is kept"
        report(failed={"step": i, "number": nums[i - 1], "error": message, **({"accepted": True} if accepted else {})},
               label=what, rest=rest(req, i + 1 if accepted else i, made))
        raise SystemExit(fixed(f"{what}: {message}", fix))

    for i, st in enumerate(req["steps"], 1):
        arg = st.get("run") or {}
        try:
            if MADE in str(arg.get("target")) and made is None:
                stop(i, f"{MADE}, but no commit_draft step before it made a commit",
                     "put a commit_draft step before it, or name the commit")
            if arg.get("action") == "approve_commit":
                approved.add(made if arg["target"] == MADE else arg["target"])
            ships = shipped_commit(arg, made) if arg.get("action") in SHIPS else None
            if ships and ships in approved and (risk := recorded_risk(ships, cwd)) != "low":
                # ADR-0050: one approval ships only a low-risk change, as checked inside this request
                stop(i, f"{ships} is not low risk ({risk}), so this approval does not ship it",
                     "read the preview, then approve a second request with the delivery steps (the workflow "
                     "leaves them in the request); do not re-run this run")
            cmd = command(st, made)
            r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
        except SystemExit:
            raise
        except Exception as e:                  # noqa: BLE001 - reported like any failed step
            stop(i, f"{type(e).__name__}: {e}", again)
        attempt = {"step": st, "returncode": r.returncode, "stdout": r.stdout[-4000:], "stderr": r.stderr[-4000:]}
        if r.returncode != 0:                   # refused or broken: undone, and in the rest
            stop(i, f"{' '.join(cmd[:6])} ...\n{r.stderr[-2000:].strip()}", again, attempt)
        done.append(attempt)
        if arg.get("action") == "commit_draft" and (c := _made(r.stdout)):
            made = c
            done[-1]["commit"] = c
        if unmet := (_unmet(r.stdout) if "run" in st else []):
            stop(i, f"{' '.join(cmd[:6])} ...\n" + "; ".join(unmet),
                 "the step's action was taken, so the rest does not send it again: fix the cause and, if the "
                 "step must be taken again (e.g. an approval was refused), add it to the rest; push the rest "
                 "and approve that run; do not re-run this run", attempt, accepted=True)
        tree = snapshot(cwd)
    report()
    return done


def record(req: dict, approver: str, person: str, run_url: str, cwd: str | Path = ".",
           outcome: dict | None = None, request: str | Path | None = None) -> dict:
    """Append the approved run, its approver and its steps to the approval-run log.

    `outcome` is what `run` printed. If a step failed, the entry says how many steps ran and which
    failed, and `request` is rewritten to the rest (`rest`), so the steps that ran are not taken
    again; otherwise the workflow removes the request."""
    from datetime import datetime, timezone
    entry = {"run": run_url, "approver": approver, "as": person, "summary": req["summary"],
             "steps": req["steps"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if outcome and outcome.get("failed"):
        entry |= {"ran": outcome["steps"], "failed": outcome["failed"]}
        if request is not None and outcome.get("rest"):
            Path(cwd, request).write_text(yaml.safe_dump(outcome["rest"], sort_keys=False, allow_unicode=True))
        elif request is not None:               # the failed step was the last, and it was taken
            Path(cwd, request).unlink(missing_ok=True)
    path = Path(cwd) / APPROVAL_RUNS
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "render", "run", "record", "change", "ship"])
    ap.add_argument("request")
    ap.add_argument("--approver", help="the GitHub login that approved the run (for run)")
    ap.add_argument("--identity", default="toprope.identity.yaml")
    ap.add_argument("--as", dest="person", help="the person the approver acted as (for record)")
    ap.add_argument("--run-url", help="the approved workflow run (for record)")
    ap.add_argument("--done", help="(for record) the JSON `run` printed; after a failed step, the request "
                                   "is rewritten to the steps that are left")
    ap.add_argument("--draft", help="the draft whose change to take through (for change)")
    ap.add_argument("--member", default="authoring", help="(for change)")
    ap.add_argument("--workspace", help="(for change) the draft's workspace, if not the member's")
    ap.add_argument("--summary", help="(for change, ship)")
    ap.add_argument("--commit", help="(for ship) the approved commit to ship")
    ap.add_argument("--domain", default="authoring", help="(for ship) the commit's domain")
    args = ap.parse_args(argv)
    if args.cmd == "ship":
        if not args.commit:
            raise SystemExit("ship needs --commit, the approved commit")
        Path(args.request).parent.mkdir(parents=True, exist_ok=True)
        Path(args.request).write_text(yaml.safe_dump(ship(args.commit, args.domain, args.summary),
                                                     sort_keys=False, allow_unicode=True))
        print(args.request)
        return
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
        outcome = json.loads(Path(args.done).read_text()) if args.done else None
        record(req, args.approver, args.person, args.run_url, outcome=outcome, request=args.request)
    else:
        if not args.approver:
            raise SystemExit("run needs --approver")
        run(req, args.approver, args.identity)


if __name__ == "__main__":
    main()
