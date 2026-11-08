"""The Toprope arm of Phase B (ADR-0040 §3–5): the same change requests, made with the generated
authoring tools and checked by the compiler.

The sandbox (a directory; its own kernel root) holds:

  toolchain/                  the self domains as approved: the tools the arm works with. Fixed for
                              the whole run, so every change is made with the same tools.
  toolchain/<member>/events/  the tools' own event logs (the Drafts are open in them)
  domains/<d>/<d>.domain.yaml the declarations the changes are made to (the Drafts' working copies)
  .toprope/commits/<d>/       their commit stores, with the approved history
  .toprope/env-<d>/           a deploy environment per domain; the approved commit is deployed first
  toprope.<d>.workspace.yaml  each domain's workspace: its only source is its interview log
  ids.yaml                    two callers: the researcher's stand-in (a person) and the editor (an
                              agent whose grant is `propose_element` only)

One change goes like this:

  edit    the stand-in records the request in each domain's interview, as the requester's words;
          the editor reads the declarations and the tool's guide, and proposes elements citing them
  check   for each domain that changed: the stand-in confirms the proposals and commits the draft;
          `check_commit` runs the compiler's change check; the commit is previewed
  deploy  passed: `approve_commit`, `deliver`, then Delivery's `preview`, `deploy` and `verify`, as
          the stand-in. Failed: the stand-in records an override approval in the sandbox (D1:
          a flag does not stop the change), and the commit is previewed and deployed through the
          kernel, whose build floor still holds. When a floor refuses, the change is recorded as
          undeployable and the working copy goes back to `main`, the last deployed state.

The stand-in is the harness, never the editor (ADR-0040 §5).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from .agent import Tool, ToolError, Transcript
from .arms import StepResult, diff, prompt, request_text, tree_hash
from .backend import Backend

DOMAINS = ("authoring", "delivery")
STANDIN = "researcher-standin <standin@m1.invalid>"
TOKENS = {"standin": "t-standin", "editor": "t-editor"}
COMPOSITION = "toolchain/toprope-self.composition.yaml"
DESCRIBED = "the declarations of two domains, changed with the Toprope authoring tool"


def _ids() -> dict[str, Any]:
    person = {"id": STANDIN, "roles": ["owner", "approver"]}
    return {TOKENS["standin"]: {**person, "kind": "person"},
            TOKENS["editor"]: {"id": "editor <editor@m1.invalid>", "kind": "agent", "roles": ["owner"],
                               "on_behalf_of": person, "grant": {"id": "editing", "actions": ["propose_element"]}}}


def _workspace(d: str) -> dict[str, Any]:
    return {"domain": f"domains/{d}/{d}.domain.yaml", "interview_log": f"domains/{d}/interview.jsonl",
            "usage_log": f"domains/{d}/sources-used.jsonl",
            "sources": [{"id": "interview", "kind": "interview-log", "path": f"domains/{d}/interview.jsonl"}]}


def build_sandbox(root: Path, out: Path) -> Path:
    """The Toprope arm's materials: each self domain as its commit store's `main` (the approved
    commit the binding names), not the repository's working copy."""
    from toprope.commits import CommitStore
    if out.exists():
        raise FileExistsError(out)
    (out / "toolchain").mkdir(parents=True)
    shutil.copy(root / "domains/toprope-self.composition.yaml", out / COMPOSITION)
    store = CommitStore(root / ".toprope/commits")
    for d in DOMAINS:
        src = root / "domains" / d
        (out / "toolchain" / d).mkdir()
        approved = store.export(d, store.main(d).id, out / "toolchain" / d / f"{d}.domain.yaml")
        shutil.copy(src / "guide.md", out / "toolchain" / d / "guide.md")
        if (src / "events").is_dir():
            shutil.copytree(src / "events", out / "toolchain" / d / "events",
                            ignore=shutil.ignore_patterns(".lock"))
        (out / "domains" / d).mkdir(parents=True)
        shutil.copy(approved, out / "domains" / d / f"{d}.domain.yaml")
        shutil.copy(src / "interview.jsonl", out / "domains" / d / "interview.jsonl")
        shutil.copytree(root / ".toprope/commits" / d, out / ".toprope/commits" / d,
                        ignore=shutil.ignore_patterns("merging.json", ".lock", ".obj-*", ".refs-*"))
        (out / f"toprope.{d}.workspace.yaml").write_text(yaml.safe_dump(_workspace(d), sort_keys=False))
    (out / "ids.yaml").write_text(yaml.safe_dump(_ids(), sort_keys=False))
    return out


def export_toolchain(root: Path, out: Path) -> Path:
    """The self domains as approved (each commit store's `main`), as a composition in `out`."""
    from toprope.commits import CommitStore
    store = CommitStore(root / ".toprope/commits")
    out.mkdir(parents=True)
    shutil.copy(root / "domains/toprope-self.composition.yaml", out / "toprope-self.composition.yaml")
    for d in DOMAINS:
        (out / d).mkdir()
        store.export(d, store.main(d).id, out / d / f"{d}.domain.yaml")
    return out


def _aside(p: Path, why: str) -> Path:
    """A free name beside `p` to move it to: `<name>.<why>-<n>`."""
    n = 1
    while (q := p.with_name(f"{p.name}.{why}-{n}")).exists():
        n += 1
    return q


def unmet(out: dict[str, Any]) -> list[str]:
    """What an accepted action set off and did not get done: a kernel call that failed or was
    refused, or a handoff that did not go through (`toprope-run` exits 0 for the action itself)."""
    return [f"{t.get('kernel') or t.get('to')}: {t.get('status')}" + (f" ({t['error']})" if t.get("error") else "")
            for t in out.get("then") or [] if t.get("status") != "ok"]


def toprope_run() -> list[str]:
    exe = Path(sys.executable).parent / "toprope-run"
    if exe.exists():
        return [str(exe)]
    return [sys.executable, "-c", "from toprope.adapters.cli import main; main()"]


class Sandbox:
    """A kernel root with the toolchain composition, its callers (`ids.yaml`) and, per domain, a
    workspace and a deploy environment."""

    def __init__(self, root: Path, tokens: dict[str, str] | None = None, reader: str = "standin"):
        self.root, self.tokens, self.reader = root, tokens or TOKENS, reader

    def run(self, who: str, member: str, domain: str, *args: str) -> dict[str, Any]:
        # `--working-copy`: the tools are the toolchain's files, fixed for the whole run. Without it a
        # member runs its deployed commit (ADR-0045), and the sandbox's commit stores are the ones
        # the arm changes, so the arm's own changes would become the tools it works with.
        cmd = [*toprope_run(), "--composition", COMPOSITION, "--working-copy", "--kernel-root", ".",
               "--identity", "static:ids.yaml",
               "--token", self.tokens[who], "--member", member, "--workspace", f"toprope.{domain}.workspace.yaml",
               "--env", f".toprope/env-{domain}", *args]
        r = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, check=False)
        try:
            out = json.loads(r.stdout) if r.stdout.strip() else {}
        except json.JSONDecodeError:
            out = {"stdout": r.stdout[-2000:]}
        if r.returncode != 0 and not out:
            out = {"status": "failed", "error": r.stderr.strip()[-2000:]}
        out.setdefault("status", "ok" if r.returncode == 0 else "failed")
        return out

    def ok(self, who: str, member: str, domain: str, *args: str) -> dict[str, Any]:
        out = self.run(who, member, domain, *args)
        if out.get("status") != "ok" or unmet(out):
            raise RuntimeError(f"{args[0]} {args[1] if len(args) > 1 else ''} failed: {json.dumps(out)[:1500]}")
        return out

    def get(self, member: str, domain: str, oid: str) -> dict[str, Any]:
        return self.run(self.reader, member, domain, "get", oid)

    def declaration(self, d: str) -> Path:
        return self.root / "domains" / d / f"{d}.domain.yaml"

    def commits(self):
        from toprope.commits import CommitStore
        return CommitStore(self.root / ".toprope/commits")

    def env(self, d: str):
        from toprope.deploy import LocalEnvironment
        return LocalEnvironment(self.root / f".toprope/env-{d}")


def toprope_tools(root: Path, ctx: dict[str, Any]) -> list[Tool]:
    """The editor's tools: read the declarations and the tool's guide, and propose elements.
    Everything else (confirming, committing, approving) is the stand-in's."""
    sb = Sandbox(root)
    seq, cites = ctx.get("seq"), ctx.get("cites") or {}

    def domain_of(domain: str) -> str:
        if domain not in DOMAINS:
            raise ToolError(f"domain is one of {', '.join(DOMAINS)}")
        return domain

    def read_declaration(domain: str) -> str:
        return sb.declaration(domain_of(domain)).read_text()

    def read_guide(domain: str) -> str:
        return (root / "toolchain" / domain_of(domain) / "guide.md").read_text()

    def propose_element(domain: str, path: str, value: str) -> dict[str, Any]:
        d = domain_of(domain)
        if not isinstance(value, str):
            value = json.dumps(value)
        try:
            json.loads(value)
        except json.JSONDecodeError as e:
            raise ToolError(f"value must be JSON: {e}") from None
        eid = f"E-{seq}-{uuid.uuid4().hex[:8]}"
        if d not in cites:
            raise ToolError(f"the change request is not recorded in {d}'s interview")
        out = sb.run("editor", "authoring", d, "propose_element", eid, "--path", path, "--origin", f"S-requests-{d}",
                     "--cites", cites[d], "--value", value)
        if out.get("status") != "ok":
            raise ToolError(json.dumps(out, ensure_ascii=False)[:3000])
        if failed := unmet(out):
            # The action was accepted, but the kernel refused to write the proposal (for example, a
            # committed domain's tools refuse a declaration with errors, #124): the editor is told.
            raise ToolError("the proposal was not written: " + "; ".join(failed))
        return {"proposed": eid, "path": path, "element": sb.get("authoring", d, eid)}

    s = {"type": "string"}
    dom = {"type": "string", "enum": list(DOMAINS)}
    return [
        Tool("read_declaration", "Read a domain's declaration as it is now (YAML), proposals included.",
             {"type": "object", "properties": {"domain": dom}, "required": ["domain"]}, read_declaration),
        Tool("read_guide", "Read the authoring tool's guide for a domain: its elements and how to work in it.",
             {"type": "object", "properties": {"domain": dom}, "required": ["domain"]}, read_guide),
        Tool("propose_element",
             "Propose a new value for one element of a domain's declaration, at a path such as "
             "`actions.confirm_element` or `invariants.<id>`. The value is the element's whole new value, "
             "as JSON. The proposal cites the change request.",
             {"type": "object", "properties": {"domain": dom, "path": s, "value": s},
              "required": ["domain", "path", "value"]}, propose_element),
    ]


class TopropeArm:
    name = "toprope"
    described = DESCRIBED

    repeat_changes = 3                             # run protocol §3: the checks run twice on 3 changes
    timed = 5                                      # run protocol §3: 5 timed repeats per change

    def __init__(self, materials: Path, work: Path, backend: Backend, resume: bool = False):
        self.backend, self.work = backend, work
        self.materials = tree_hash(materials)
        self.sb = Sandbox(work / "sandbox")
        if resume:
            if not self.sb.root.is_dir():
                raise FileNotFoundError(f"nothing to resume in {work}")
            self._back_to_deployed()                   # a change left half done starts again
        else:
            if self.sb.root.exists():
                if (self.sb.root / "ids.yaml").exists():           # copied from the materials: a run
                    raise FileExistsError(f"{work} has a run: resume it, or start a new run directory")
                # Only what git ignores is left (caches such as `.hypothesis/`, from a run moved
                # away with `git mv`): not a run. Kept aside, never deleted.
                self.sb.root.rename(_aside(self.sb.root, "stale"))
            shutil.copytree(materials, self.sb.root)
            self._start()
        self._before: dict[str, str] = {}
        self._cites: dict[str, str] = {}
        self._commits: dict[str, dict[str, Any]] = {}
        self._failed: dict[str, dict[str, Any]] = {}

    def materials_hash(self) -> str:
        return self.materials

    # -- setup ---------------------------------------------------------------------------------
    def _start(self) -> None:
        """Deploy what is approved, so each environment has a current commit, and add each
        domain's interview as the source the editor cites."""
        from toprope.types import Actor
        st = self.sb.commits()
        for d in DOMAINS:
            main = st.main(d)
            env = self.sb.env(d)
            env.preview_commit(st, d, main.id)
            env.deploy_commit(st, d, main.id, Actor(STANDIN, "person"))
            self.sb.ok("standin", "authoring", d, "add_source", f"S-requests-{d}", "--kind", "interview-log",
                       "--path", f"domains/{d}/interview.jsonl")

    def _back_to_deployed(self, domains: tuple[str, ...] = DOMAINS) -> None:
        """The working copy as the environment runs it: the last deployed state. (`main` may be
        ahead of it when a deploy failed after its approval.)"""
        st = self.sb.commits()
        for d in domains:
            st.checkout(d, self.sb.env(d).current()["commit"], self.sb.declaration(d), force=True)

    def _texts(self) -> dict[str, str]:
        return {f"{d}.domain.yaml": self.sb.declaration(d).read_text() for d in DOMAINS}

    # -- the three steps -------------------------------------------------------------------------
    def edit(self, req: dict[str, Any], out: Path) -> StepResult:
        self._before = self._texts()
        tag = uuid.uuid4().hex[:6]
        for d in DOMAINS:                              # the request, in the requester's words
            q, a = f"Q-cr-{req['seq']}-{d}-{tag}", f"A-cr-{req['seq']}-{d}-{tag}"
            self.sb.ok("standin", "authoring", d, "ask_question", q, "--stage", "actions",
                       "--text", f"Change request {req['seq']}")
            self.sb.ok("standin", "authoring", d, "answer_question", a, "--question", q,
                       "--words", request_text(req), "--decisions", "[]")
            self._cites[d] = self.sb.get("authoring", d, a)["ref"]
        from .toolserver import ToolSpec
        t = time.monotonic()                           # the editor's time, not the bookkeeping's
        spec = ToolSpec("toprope", str(self.sb.root), json.dumps({"seq": req["seq"], "cites": self._cites}))
        summary = self.backend.converse(prompt("edit_toprope", arm=self.described), request_text(req), spec,
                                        Transcript(out / "edit.jsonl"))
        changed = diff(self._before, self._texts())
        return StepResult(time.monotonic() - t, {"summary": summary, "diff": changed, "changed": bool(changed)})

    def check(self, req: dict[str, Any], out: Path) -> StepResult:
        from toprope.check import change_check
        from toprope.incremental import ResultCache
        after = self._texts()
        changed = [d for d in DOMAINS if after[f"{d}.domain.yaml"] != self._before[f"{d}.domain.yaml"]]
        findings: list[dict[str, Any]] = []
        self._commits, self._failed = {}, {}
        timings: dict[str, Any] = {}
        t0 = time.monotonic()
        for d in changed:
            t = time.monotonic()
            confirmed = self.sb.run("standin", "authoring", d, "confirm_all_proposed", d)
            if confirmed["status"] != "ok":
                self._failed[d] = {"commit": None, "error": "confirm_all_proposed failed", "out": confirmed}
                continue
            made = self.sb.run("standin", "authoring", d, "commit_draft", d)
            cid = next((x["object"] for x in made.get("then", []) if x.get("object")), None)
            if made["status"] != "ok" or cid is None:
                self._failed[d] = {"commit": None, "error": "commit_draft made no commit", "out": made}
                continue
            checked = self.sb.ok("standin", "authoring", d, "check_commit", cid)
            passed = bool(self.sb.get("authoring", d, cid).get("checks_passed"))
            timings[d] = {"commit_and_check": time.monotonic() - t}
            # The problems in detail: the action records only a summary, so the same check runs
            # again here, read-only and from the same cache. Should the two runs disagree (the
            # exploration samples examples), both verdicts are recorded.
            st = self.sb.commits()
            env = self.sb.env(d)
            with env.events(d) as events:
                report = change_check(st.domain(d, cid), st.domain(d, st.review_base(d, cid)), events=events,
                                      cache=ResultCache(self.sb.root / ".toprope/cache"))
            for name, res in report.checks.items():
                for p in res.problems:
                    findings.append({"domain": d, "check": name, "severity": p.severity, "where": p.where,
                                     "problem": p.message})
            t = time.monotonic()
            try:
                build = env.preview_commit(st, d, cid)
                preview = {"ok": build.harness_ok, "build": build.id}
            except Exception as e:                       # noqa: BLE001 - a refused build is a finding too
                preview = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            timings[d]["preview"] = time.monotonic() - t
            self._commits[d] = {"commit": cid, "passed": passed, "detail_passed": report.ok,
                                "verdicts_agree": passed == report.ok, "preview": preview,
                                "check": list(checked.get("then", [])), "timings": report.timings}
        for d in self._failed:                         # no commit: back to what is deployed
            self._back_to_deployed((d,))
        seconds = time.monotonic() - t0
        data: dict[str, Any] = {"findings": findings, "commits": self._commits, "not_committed": self._failed,
                                "changed_domains": changed, "timings": timings,
                                "runs": [{"run": 1, "findings": findings}]}     # derandomized: one run
        if self._commits and self._repeats_done() < self.repeat_changes:
            data["repeat"] = self._repeat(findings)
        if self._commits:
            data["timed"] = [self._timed() for _ in range(self.timed)]
        return StepResult(seconds, data)

    def _repeats_done(self) -> int:
        n = 0
        for f in self.work.glob("seq-*/record.json"):
            n += "repeat" in (json.loads(f.read_text()).get("check") or {})
        return n

    def _report(self, d: str, cid: str, cached: bool) -> Any:
        from toprope.check import change_check
        from toprope.incremental import ResultCache
        st, env = self.sb.commits(), self.sb.env(d)
        with env.events(d) as events:
            return change_check(st.domain(d, cid), st.domain(d, st.review_base(d, cid)), events=events,
                                cache=ResultCache(self.sb.root / ".toprope/cache") if cached else None)

    def _repeat(self, first: list[dict[str, Any]]) -> dict[str, Any]:
        """Run protocol §3: a second run of the checks, uncached, must find the same."""
        again = [{"domain": d, "check": name, "severity": p.severity, "where": p.where, "problem": p.message}
                 for d, c in self._commits.items() for name, res in self._report(d, c["commit"], False).checks.items()
                 for p in res.problems]
        key = lambda f: json.dumps(f, sort_keys=True)                  # noqa: E731
        a, b = {key(f) for f in first}, {key(f) for f in again}
        return {"same": a == b, "only_first": sorted(a - b), "only_second": sorted(b - a)}

    def _timed(self) -> dict[str, Any]:
        """One timed repeat of edit's end → validated preview, for each changed domain (run protocol
        §3, "Name the limiter"): the impact report and the affected harness (from the change check,
        with the result cache, as in use) and the preview build."""
        st = self.sb.commits()
        out: dict[str, Any] = {"seconds": 0.0, "parts": {}}
        for d, c in self._commits.items():
            t = time.monotonic()
            report = self._report(d, c["commit"], True)
            check_s = time.monotonic() - t
            t = time.monotonic()
            try:
                self.sb.env(d).preview_commit(st, d, c["commit"])
            except Exception:                            # noqa: BLE001 - timed all the same
                pass
            preview_s = time.monotonic() - t
            parts = {"impact": report.timings.get("impact") or 0.0, "harness": report.timings.get("harness") or 0.0,
                     "preview": preview_s}
            parts["other_check"] = max(0.0, check_s - parts["impact"] - parts["harness"])
            out["parts"][d] = parts
            out["seconds"] += check_s + preview_s
        totals: dict[str, float] = {}
        for parts in out["parts"].values():
            for k, v in parts.items():
                totals[k] = totals.get(k, 0.0) + v
        out["limiter"] = max(totals, key=lambda k: totals[k]) if totals else None
        return out

    def deploy(self, req: dict[str, Any], out: Path) -> StepResult:
        t = time.monotonic()
        result: dict[str, Any] = {}
        for d, c in self._commits.items():
            result[d] = self._approved_path(d, c) if c["passed"] else self._override(d, c)
            if not result[d].get("deployed"):
                self._back_to_deployed((d,))
        return StepResult(time.monotonic() - t, {"deployed": all(r.get("deployed") for r in result.values()),
                                                 "domains": result})

    def _approved_path(self, d: str, c: dict[str, Any]) -> dict[str, Any]:
        cid = c["commit"]
        steps = {"approve_commit": self.sb.run("standin", "authoring", d, "approve_commit", cid)}
        if steps["approve_commit"]["status"] != "ok":
            return {"deployed": False, "path": "approved", "steps": steps}
        handed = self.sb.run("standin", "authoring", d, "deliver", cid, "--environment", "local")
        steps["deliver"] = handed
        request = next((x["object"] for x in handed.get("then", []) if x.get("object")), None)
        if handed["status"] != "ok" or request is None:
            return {"deployed": False, "path": "approved", "steps": steps}
        for action in ("preview", "deploy"):
            steps[action] = self.sb.run("standin", "delivery", d, action, request)
            if steps[action]["status"] != "ok":
                return {"deployed": False, "path": "approved", "steps": steps}
        deployed = (self.sb.env(d).current() or {}).get("commit") == cid
        if deployed:
            steps["verify"] = self.sb.run("standin", "delivery", d, "verify", request, "--verified", "true")
        return {"deployed": deployed, "path": "approved", "request": request, "steps": steps}

    def _override(self, d: str, c: dict[str, Any]) -> dict[str, Any]:
        """D1: the change goes out though the check flagged it. The stand-in's approval is
        recorded in the sandbox's commit store; the kernel's build floor still decides."""
        from toprope.commits import CommitError
        from toprope.deploy import DeployRefused
        from toprope.types import Actor
        st, env = self.sb.commits(), self.sb.env(d)
        if not c["preview"].get("ok"):                 # the build floor first: approve only what can go out
            return {"deployed": False, "path": "override",
                    "refused": f"harness: the build did not pass ({c['preview']})"}
        try:
            approved = st.approve(d, c["commit"], STANDIN)
            target = approved.id if approved else c["commit"]
            if target != c["commit"]:
                env.preview_commit(st, d, target)
            env.deploy_commit(st, d, target, Actor(STANDIN, "person"))
        except (CommitError, DeployRefused) as e:
            return {"deployed": False, "path": "override", "refused": f"{type(e).__name__}: {e}"}
        return {"deployed": True, "path": "override", "commit": target}

    def probe(self, req: dict[str, Any], out: Path, worlds: Path, probes: list[dict[str, Any]],
              jobs: int = 1) -> list[dict[str, Any]]:
        """The probes after this change, through the tools generated from what is deployed."""
        from .probes import run_probes
        toolchain = _deployed(self.sb, out / "deployed-toolchain")
        guides = _guides(toolchain)
        return run_probes(self.backend, worlds, probes, out, "the Toprope tools generated from these "
                          "domains (their MCP tools)", guides, toolchain, jobs=jobs)


def _deployed(sb: Sandbox, out: Path) -> Path:
    """The declarations the environments run now, as a composition: the probes' tools."""
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copy(sb.root / COMPOSITION, out / "toprope-self.composition.yaml")
    for d in DOMAINS:
        (out / d).mkdir()
        shutil.copy(sb.env(d).current()["declaration"], out / d / f"{d}.domain.yaml")
    return out


def _guides(toolchain: Path) -> str:
    """The generated how-to-work guides of the deployed domains."""
    import subprocess as sp
    parts = []
    for d in DOMAINS:
        r = sp.run([*toprope_run(), "--composition", str(toolchain / "toprope-self.composition.yaml"), "--member", d,
                    "--store", "memory", "--identity", "static:/dev/null", "guide"],
                   capture_output=True, text=True, check=False)
        parts.append(r.stdout if r.returncode == 0 else f"(the {d} guide could not be generated: {r.stderr[-500:]})")
    return "\n\n".join(parts)


def toprope_arm(materials: Path, work: Path, backend: Backend, resume: bool = False) -> TopropeArm:
    return TopropeArm(materials, work, backend, resume)
