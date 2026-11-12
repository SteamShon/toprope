"""Run a human request: steps only the researcher may take, approved in GitHub (ADR-0039).

A request is a file `.toprope/requests/<id>.yaml` on a work branch:

    summary: Freeze the M1 binding
    steps:
      - freeze-binding: experiments/m1/instruments
      - run: {member: authoring, action: check_commit, target: 5-ab12cd34ef56ab78}
      - run: {member: authoring, action: approve_commit, target: 5-ab12cd34ef56ab78}
      - run: {member: authoring, action: confirm_all_proposed, target: authoring}

Steps, from a fixed set:
- `freeze: DIR`, `freeze-binding: DIR`, `freeze-protocol: DIR`, `freeze-prereg: DIR` (M2's
  preregistration): `experiments/tools/instruments.py`
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

Without GitHub (ADR-0053, 3): a person applies a request at their own terminal with
`toprope-apply REQUEST`, which calls `apply` here. It shows `render`, asks for one confirmation
(`yes`), runs `run` as the person whose git email `toprope.identity.yaml` lists (`channel:
local`), and `record`s the run with `channel: local`, so F1 counts it as one approval. It refuses
without a terminal, and for a caller who is not a person. A commit not recorded low risk is not
taken past its preview on the same confirmation (ADR-0050, 3): `run` holds there, the request keeps
deploy, the probes and verify, and the person applies it again after reading the preview.

  python tools/human_request.py apply REQUEST [--identity toprope.identity.yaml] [--ship]
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
from toprope.errors import fixed

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = ".toprope/requests"
APPROVAL_RUNS = ".toprope/approval-runs.jsonl"
FREEZE_STEPS = ("freeze", "freeze-binding", "freeze-protocol", "freeze-prereg")
INSTRUMENT_STEPS = (*FREEZE_STEPS, "amend")
COMPOSITION = "domains/toprope-self.composition.yaml"
MADE = "$commit"                     # the commit an earlier commit_draft step of the request made
AGAIN = ("fix the cause, then push a change to the request (the workflow leaves the steps that did not run in it), "
         "and approve that run; do not re-run this run")   # the fix of a step that failed
TLC_ENV = "TOPROPE_TLC_JAR"         # the kernel model-checks with it; approval needs it (ADR-0043)
LOCAL_AGAIN = "fix the cause, then apply the request again (it now holds only the steps that did not run)"
TAKEN = ("the step's action was taken, so the rest does not send it again: fix the cause and, if the step must "
         "be taken again (e.g. an approval was refused), add it to the rest; ")
CHANNELS = ("github", "local")      # how a request was approved: the workflow, or `apply` at a terminal


def load(path: str | Path) -> dict:
    req = yaml.safe_load(Path(path).read_text())
    errors = check(req)
    if errors:
        raise ValueError(fixed("; ".join(errors), "edit the request into the format at the top of "
                               "tools/human_request.py, then push it again"))
    return req


def check(req: object) -> list[str]:
    """Errors in a request; empty means it may be shown for approval."""
    if not isinstance(req, dict) or set(req) - {"summary", "steps", "risk"}:
        return ["a request has `summary` and `steps` (and the `risk` the change check found), nothing else"]
    errors = []
    risk = req.get("risk", {"level": "low", "reasons": []})
    if not isinstance(risk, dict) or set(risk) != {"level", "reasons"} or not isinstance(risk["level"], str) \
            or not isinstance(risk["reasons"], list) or not all(isinstance(r, str) for r in risk["reasons"]):
        errors.append("risk: `level` and a list of `reasons`, as toprope-change writes it")
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
        if kind in FREEZE_STEPS:
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


def render(req: dict, cwd: str | Path = ".", channel: str = "github") -> str:
    """What the researcher reads on the run page before approving, and a person applying the
    request at a terminal reads before confirming (`apply`, `channel` local: there a commit not low
    risk is held after its preview instead of refused at its delivery)."""
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
        if channel == "local":
            lines += ["", "**One confirmation ships this change if it is low risk** (ADR-0050): deliver and "
                      "preview run in any case; if the check in this request records the commit as not low risk, "
                      "the run is held after the preview, and deploy, the probes and verify wait for a second "
                      "apply. `verify` runs only if the probes passed; confirming verifies in advance on that "
                      "condition."]
        else:
            lines += ["", "**One approval ships this change** (ADR-0050): the delivery steps run only if the "
                      "check in this request finds it low risk, and `verify` runs only if the probes passed; "
                      "approving verifies in advance on that condition."]
    lines += risk_lines(req, cwd)
    for st in req["steps"]:                      # what a confirm step confirms, as one diff (B5)
        (kind, arg), = st.items()
        if kind == "run" and arg.get("action") in ("confirm_all_proposed", "confirm_element"):
            lines += ["", f"#### What `{arg['action']}` confirms", "", "```diff",
                      review(arg.get("workspace") or f"toprope.{arg['member']}.workspace.yaml", cwd).rstrip(), "```"]
    return "\n".join(lines) + "\n"


def risk_lines(req: dict, cwd: str | Path = ".") -> list[str]:
    """The risk, and its reasons, that the person reads before approving (ADR-0050, 4): what the
    change check found before the request was written, and what `check_commit` recorded on each
    commit the request names. A commit the request makes has its risk recorded inside it."""
    lines = []
    if isinstance(req.get("risk"), dict):
        r = req["risk"]
        lines += ["", f"**Risk written in the request: {r['level']}**"
                  + (": " + "; ".join(r["reasons"]) if r["reasons"] else "")
                  + ". Written by whoever wrote the request (the change check's view), not the kernel's record: "
                  "the `check_commit` step in this request records the risk that counts."]
    if any(MADE in str((st.get("run") or {}).get("target")) for st in req["steps"]
           if (st.get("run") or {}).get("action") in SHIPS):
        lines += ["", "**The commit this request makes has no recorded risk yet.** Its `check_commit` step "
                  "records it; the delivery depends on what that check records."]
    named = []
    for st in req["steps"]:
        arg = st.get("run") or {}
        c = arg.get("target") if arg.get("action") in ("check_commit", "approve_commit") else \
            shipped_commit(arg, None) if arg.get("action") in SHIPS else None
        if c and MADE not in c and c not in named:
            named.append(c)
    for c in named:
        try:
            row = recorded_risk_row(c, cwd)
        except (OSError, ValueError):            # the page still shows the steps
            row = None
        lines += ["", f"**Risk recorded on `{c}`:** " + (row if row else "none recorded yet")]
    return lines


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


def command(st: dict, made: str | None = None, identity: str = "github") -> list[str]:
    tool = [sys.executable, str(ROOT / "experiments/tools/instruments.py")]
    (kind, arg), = st.items()
    if kind in FREEZE_STEPS:
        return tool + [kind, arg]
    if kind == "amend":
        return tool + ["amend", arg["dir"], arg["file"], "--reason", arg["reason"]]
    target = arg["target"].replace(MADE, made) if made else arg["target"]
    cmd = ["toprope-run", "--composition", COMPOSITION, "--member", arg["member"],
           "--kernel-root", ".", "--workspace", arg.get("workspace") or f"toprope.{arg['member']}.workspace.yaml",
           "--env", ".toprope/env", "--identity", identity, arg["action"], target]
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


def recorded_risk_row(commit: str, cwd: str | Path = ".") -> str | None:
    """The risk `check_commit` last recorded on a commit (ADR-0050), from any domain's checks, with
    its reasons: `low`, or `high: <reasons>`."""
    found = None
    for path in sorted((Path(cwd) / ".toprope" / "commits").glob("*/checks.jsonl")):
        for line in path.read_text().splitlines():
            row = json.loads(line) if line.strip() else {}
            if row.get("commit") == commit and row.get("check") == "risk":
                found = str(row.get("summary", ""))
    return found


def recorded_risk(commit: str, cwd: str | Path = ".") -> str | None:
    """The risk level `check_commit` last recorded on a commit (ADR-0050)."""
    row = recorded_risk_row(commit, cwd)
    return None if row is None else row.split(":", 1)[0].strip()


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


HELD = ("deploy", "run_probes", "verify")   # what puts a commit in use, after its preview


def run(req: dict, approver: str, identity: str = "toprope.identity.yaml", cwd: str | Path = ".",
        channel: str = "github", token: str | None = None, outcome: dict | None = None) -> list[dict]:
    """Run every step as the approver; stop at the first that fails.

    `channel` is how the request was approved. `github` (the workflow): `approver` is the GitHub
    login that approved the run, and the steps run with `--identity github`. `local` (`apply`, at
    a person's terminal): `approver` is the person's git email, the steps run with `--identity
    git:<identity>`, and `token` is the confirmation `apply` took, so `toprope-run` does not ask
    for it again on each person-only step. Locally, a commit not recorded low risk is held after
    its preview: the run stops before its deploy, run_probes or verify, which wait for a second
    confirmation, given after the person read the preview (ADR-0050, 3). The workflow refuses the
    delivery steps of such a commit approved in the same request instead.

    It prints what happened as JSON on stdout (into `outcome` instead, when given), also when a
    step fails: `as`, `steps` (how many
    ran: the first `steps` of this request), `of`, `commit`, and on failure `failed` (`step`: its
    position in this request; `number`: its number in the first request, as `label` gives it; why;
    and `accepted` when its action was taken but what it set off failed, so it is one of the
    `steps` that ran), `label` (what happened, in the first
    request's step numbers) and `rest` (the request that is left, see `rest`; null if none). A run
    held after a preview has `held` (the step it stopped before, the commit and its risk), `label`
    and `rest`, and returns. Then
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
    local = channel == "local"
    if channel not in CHANNELS:
        raise ValueError(fixed(f"channel {channel!r}", f"use one of {', '.join(CHANNELS)}"))
    if local:
        from toprope.adapters.cli.apply import APPLY_ENV
        from toprope.identity.git import load_table
        person = load_table(Path(cwd) / identity).get(approver)
        if person is None or person.actor.kind != "person":
            raise SystemExit(fixed(f"{approver} is not a person in {identity}",
                                   "apply the request as a person listed under `people` there"))
        env = {**os.environ, APPLY_ENV: token or ""}
        ident = f"git:{identity}"
    else:
        person = github_logins(Path(cwd) / identity).get(approver.lower())
        if person is None:
            raise SystemExit(fixed(f"GitHub user {approver} approved, but is not a person with `github:` in {identity}",
                                   "add `github: <login>` to the approver's entry under `people` in the identity file, "
                                   "or have a listed person approve"))
        env = {**os.environ, ENV: approver}
        ident = "github"
    if any((st.get("run") or {}).get("action") == "approve_commit" for st in req["steps"]) \
            and not env.get(TLC_ENV):
        raise SystemExit(fixed(f"approve_commit needs TLC: set {TLC_ENV} to a TLC jar (the workflow does)",
                               "run the request through the `human-request` workflow, or set the variable to a TLC "
                               "jar"))
    _, nums, total = numbering(req)
    done, made, approved, previewed = [], None, set(), set()
    tree = snapshot(cwd)

    def report(**more) -> None:
        out = {"approver": approver, "as": person.actor.id, "steps": len(done), "of": len(req["steps"]),
               "channel": channel, **({"commit": made} if made else {}), **more}
        if outcome is None:
            print(json.dumps(out, indent=2))
        else:
            outcome.clear()
            outcome.update(out)

    def stop(i: int, message: str, fix: str, attempt: dict | None = None, accepted: bool = False) -> None:
        if not local:                            # the workflow's log; a person reads the message below
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

    i = 0
    try:                                        # Ctrl-C stops it like a failed step: work kept, rest left
        for i, st in enumerate(req["steps"], 1):
            arg = st.get("run") or {}
            try:
                if MADE in str(arg.get("target")) and made is None:
                    stop(i, f"{MADE}, but no commit_draft step before it made a commit",
                         "put a commit_draft step before it, or name the commit")
                if arg.get("action") == "approve_commit":
                    approved.add(made if arg["target"] == MADE else arg["target"])
                ships = shipped_commit(arg, made) if arg.get("action") in SHIPS else None
                risk = recorded_risk(ships, cwd) if ships else None
                if local and ships and risk != "low" and arg["action"] in HELD and (ships in approved or ships in previewed):
                    # ADR-0050, 3: the person reads the preview before the commit is put in use
                    held = f"held before step {nums[i - 1]} of {total}: {ships} is not low risk ({risk})"
                    if done:
                        held += f"; {_spans(nums[:len(done)])} ran and {'its' if len(done) == 1 else 'their'} work is kept"
                    report(held={"step": i, "number": nums[i - 1], "commit": ships, "risk": risk},
                           label=held, rest=rest(req, i, made))
                    return done
                if not local and ships and ships in approved and risk != "low":
                    # ADR-0050: one approval ships only a low-risk change, as checked inside this request
                    stop(i, f"{ships} is not low risk ({risk}), so this approval does not ship it",
                         "read the preview, then approve a second request with the delivery steps (the workflow "
                         "leaves them in the request); do not re-run this run")
                cmd = command(st, made, ident)
                r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
            except SystemExit:
                raise
            except Exception as e:                  # noqa: BLE001 - reported like any failed step
                if local:
                    stop(i, f"{type(e).__name__}: {e}", LOCAL_AGAIN)
                stop(i, f"{type(e).__name__}: {e}", AGAIN)
            attempt = {"step": st, "returncode": r.returncode, "stdout": r.stdout[-4000:], "stderr": r.stderr[-4000:]}
            if r.returncode != 0:                   # refused or broken: undone, and in the rest
                why = f"{' '.join(cmd[:6])} ...\n{r.stderr[-2000:].strip()}"
                if local:
                    stop(i, why, LOCAL_AGAIN, attempt)
                stop(i, why, AGAIN, attempt)
            done.append(attempt)
            if arg.get("action") == "commit_draft" and (c := _made(r.stdout)):
                made = c
                done[-1]["commit"] = c
            if arg.get("action") == "preview" and ships:
                previewed.add(ships)
            if unmet := (_unmet(r.stdout) if "run" in st else []):
                why = f"{' '.join(cmd[:6])} ...\n" + "; ".join(unmet)
                if local:
                    stop(i, why, TAKEN + "then apply the request again", attempt, accepted=True)
                stop(i, why, TAKEN + "push the rest and approve that run; do not re-run this run", attempt, accepted=True)
            tree = snapshot(cwd)
    except KeyboardInterrupt:
        taken = 0 < i <= len(done)              # the step had run when the interrupt came
        if local:
            stop(max(i, 1), "interrupted (Ctrl-C)", LOCAL_AGAIN, accepted=taken)
        stop(max(i, 1), "interrupted (Ctrl-C)", AGAIN, accepted=taken)
    report()
    return done


def record(req: dict, approver: str, person: str, run_url: str, cwd: str | Path = ".",
           outcome: dict | None = None, request: str | Path | None = None, channel: str = "github") -> dict:
    """Append the approved run, its approver and its steps to the approval-run log.

    `outcome` is what `run` printed. If a step failed, or a local run was held after a preview, the
    entry says how many steps ran and which failed (or where it was held), and `request` is
    rewritten to the rest (`rest`), so the steps that ran are not taken again; otherwise the
    workflow (or `apply`) removes the request. `channel` is how it was approved: `github` (the
    workflow) or `local` (`apply`, at the person's terminal); F1 counts either as one approval."""
    from datetime import datetime, timezone
    entry = {"run": run_url, "approver": approver, "as": person, "summary": req["summary"],
             "steps": req["steps"], "channel": channel, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if outcome and (outcome.get("failed") or outcome.get("held")):
        entry |= {"ran": outcome["steps"], **{k: outcome[k] for k in ("failed", "held") if outcome.get(k)}}
        if request is not None and outcome.get("rest"):
            Path(cwd, request).write_text(yaml.safe_dump(outcome["rest"], sort_keys=False, allow_unicode=True))
        elif request is not None:               # the failed step was the last, and it was taken
            Path(cwd, request).unlink(missing_ok=True)
    path = Path(cwd) / APPROVAL_RUNS
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def with_delivery(req: dict) -> dict:
    """The request with the delivery steps of the commit it makes (`apply --ship`): deliver, preview,
    deploy, run the probes, verify. Applied locally, a commit not recorded low risk stops after its
    preview, so a high-risk change takes two confirmations, the second after the preview was read."""
    runs = [st["run"] for st in req["steps"] if "run" in st]
    if any(a["action"] in SHIPS for a in runs):
        return req
    drafts = [a for a in runs if a["action"] == "commit_draft"]
    if not drafts or not any(a["action"] == "approve_commit" and a["target"] == MADE for a in runs):
        raise SystemExit(fixed("--ship adds the delivery of the commit the request makes and approves; this request "
                               "makes none", "leave --ship out, or write the delivery request with "
                               "`python tools/human_request.py ship`"))
    return {**req, "steps": [*req["steps"], *ship(MADE, drafts[-1]["target"])["steps"]]}


def apply(request: str | Path, identity: str = "toprope.identity.yaml", cwd: str | Path = ".",
          with_ship: bool = False, ask=input) -> dict:
    """A person applies a request at their own terminal (ADR-0053, 3): one confirmation, then the
    steps as that person, recorded as one approval (`channel: local`).

    It shows the request as the run page does (`render`), asks for `yes` once, runs it (`run`,
    `channel: local`), records the run (`record`) and removes the request; after a failed step, or
    a hold after a preview, the request keeps the steps that are left. It refuses without a
    terminal, and for a caller whose git email the identity file does not list as a person. Returns
    what `run` reported."""
    import uuid

    sys.path.insert(0, str(ROOT / "src"))
    from toprope.adapters.cli.apply import confirmation
    from toprope.identity.git import GitIdentity
    if not sys.stdin.isatty():
        raise SystemExit(fixed("applying a request needs a person at a terminal, and this process has none",
                               "run `toprope-apply` yourself, on your terminal; or commit and push the request, "
                               "and approve its run in GitHub (the `human-request` workflow)"))
    try:
        req = load(Path(cwd) / request)
    except (OSError, ValueError, yaml.YAMLError) as e:
        raise SystemExit(fixed(f"{request}: {e}", "give the path of a request file, such as "
                               ".toprope/requests/<id>.yaml")) from None
    try:
        ident = GitIdentity(Path(cwd) / identity, root=cwd, once=True)
    except (OSError, ValueError) as e:
        raise SystemExit(fixed(f"identity file {identity}: {e}", "give --identity the repository's identity file")) from None
    caller = ident.resolve()
    if caller is None:
        raise SystemExit(fixed(ident.explain(), "apply the request from a git identity listed under `people`"))
    if caller.actor.kind != "person":
        raise SystemExit(fixed(f"{caller.actor.id} is an agent: only a person applies a request (ADR-0041)",
                               "ask the person to apply it on their own terminal, or push it and have them approve "
                               "its run in GitHub (the `human-request` workflow)"))
    if with_ship:
        req = with_delivery(req)
    if any((st.get("run") or {}).get("action") == "approve_commit" for st in req["steps"]) \
            and not os.environ.get(TLC_ENV):
        raise SystemExit(fixed(f"approve_commit needs TLC's check, and {TLC_ENV} is not set: nothing was run",
                               f"set {TLC_ENV} to a TLC jar (tla2tools.jar, as the tla workflow pins it), then "
                               "apply again"))
    print(render(req, cwd, "local"), end="")
    actions = [(st.get("run") or {}).get("action") for st in req["steps"]]
    if "preview" in actions and set(HELD) & set(actions[actions.index("preview"):]):
        print("\nIf the commit is not recorded low risk (a commit this request makes has no recorded risk until "
              "its check runs), this stops after its preview: read it, then apply the request again for deploy, "
              "the probes and verify (ADR-0050, 3).")
    email = ident.email()
    answer = ask(f"\nTake these {len(req['steps'])} steps as {caller.actor.id}? Type `yes` to apply: ")
    if answer.strip() != "yes":
        raise SystemExit(fixed("not applied: nothing was run", "type `yes` to apply it"))
    outcome: dict = {}
    url = f"local:{uuid.uuid4().hex[:12]}"
    with confirmation(caller.actor.id) as token:
        try:
            done = run(req, email, identity, cwd, channel="local", token=token, outcome=outcome)
        except BaseException:                   # a failed step, Ctrl-C, SIGTERM: record what ran
            if outcome.get("steps"):            # as the workflow: nothing is recorded if no step ran
                record(req, email, caller.actor.id, url, cwd, outcome, request, channel="local")
            raise
    record(req, email, caller.actor.id, url, cwd, outcome, request, channel="local")
    if outcome.get("held"):
        preview = next((d["stdout"] for d in reversed(done) if (d["step"].get("run") or {}).get("action") == "preview"), "")
        print(f"\n#### The preview\n\n{preview.strip()}\n" if preview else "")
        print(f"{outcome['label']}. Read the preview; then `toprope-apply {request}` takes the steps left in it.")
    else:
        Path(cwd, request).unlink(missing_ok=True)
        print(f"Applied: {len(done)} steps as {caller.actor.id}, recorded as {url} in {APPROVAL_RUNS}. "
              "Commit the result with the logs it changed.")
    return outcome


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "render", "run", "record", "change", "ship", "apply"])
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
    ap.add_argument("--ship", action="store_true", help="(for apply) add the delivery of the commit the request "
                                                         "makes; a commit not low risk stops after its preview")
    args = ap.parse_args(argv)
    if args.cmd == "apply":
        apply(args.request, args.identity, with_ship=args.ship)
        return
    if args.cmd == "ship":
        if not args.commit:
            raise SystemExit(fixed("ship needs --commit, the approved commit",
                                   "give --commit with the approved commit's id"))
        Path(args.request).parent.mkdir(parents=True, exist_ok=True)
        Path(args.request).write_text(yaml.safe_dump(ship(args.commit, args.domain, args.summary),
                                                     sort_keys=False, allow_unicode=True))
        print(args.request)
        return
    if args.cmd == "change":
        if not args.draft:
            raise SystemExit(fixed("change needs --draft",
                                   "give --draft with the draft whose change to take through"))
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
            raise SystemExit(fixed("record needs --approver, --as and --run-url",
                                   "give --approver, --as and --run-url (the workflow does)"))
        outcome = json.loads(Path(args.done).read_text()) if args.done else None
        record(req, args.approver, args.person, args.run_url, outcome=outcome, request=args.request)
    else:
        if not args.approver:
            raise SystemExit(fixed("run needs --approver",
                                   "give --approver with the GitHub login that approved the run (the workflow does)"))
        run(req, args.approver, args.identity)


if __name__ == "__main__":
    main()
