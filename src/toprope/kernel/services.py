"""The kernel-service port (ADR-0028) and its adapters.

- `RecordingKernel`: deterministic; records every call and returns a successful result
  (or a configured one). The regeneration check and tests use it.
- `LocalKernel`: the real services, on files under one root directory. Paths in inputs are
  relative to that root, and never leave it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from ..errors import fixed
from . import Service
from . import service as lookup


def complete(svc: Service, result: dict[str, Any]) -> dict[str, Any]:
    """Every field, always (ADR-0028): defaults for what a result leaves out."""
    full = {**svc.failure(""), **{k: v for k, v in result.items() if k in svc.fields()}}
    full["ok"] = bool(result.get("ok", True))
    full["error"] = str(result.get("error") or "")
    return full


APPROVAL_RUNS = ".toprope/approval-runs.jsonl"   # written by tools/human_request.py (ADR-0039)

_CALLER: ContextVar[dict[str, Any] | None] = ContextVar("kernel_caller", default=None)


class KernelServices(ABC):
    @property
    def caller(self) -> dict[str, Any] | None:
        """Who made the current call (per call, safe across threads): a commit's author."""
        return _CALLER.get()

    def call(self, service: str, inputs: dict[str, Any], caller: dict[str, Any] | None = None) -> dict[str, Any]:
        """`caller` is the actor whose action made the call (`{id, kind}`), from the outbox
        event. Services that record a person's decision check it, so no declaration can make
        an agent, the system or the kernel approve or deploy (the fixed floor)."""
        svc = lookup(service)
        if svc is None:
            raise KeyError(fixed(f"no kernel service {service!r}", "use a service the kernel's catalog lists (src/toprope/kernel/__init__.py)"))
        missing = [i for i in svc.required() if i not in inputs]
        if missing:
            return svc.failure(fixed(f"missing inputs {missing}", "map them in the effect's `inputs` in the declaration"))
        if "approver" in svc.inputs and not service.startswith("mcp:"):   # an upstream tool's own argument
            if not caller or caller.get("kind") != "person" or caller.get("id") != inputs["approver"]:
                return svc.failure(fixed(f"{service} records a person's decision: the calling person must be the approver",
                                         "the person named as approver takes the action themselves"))
        token = _CALLER.set(caller)
        try:
            return complete(svc, self.run(service, {k: inputs[k] for k in svc.inputs if k in inputs}))
        except Exception as e:   # a failure still replies: the declaration decides what it means
            return svc.failure(f"{type(e).__name__}: {e}")
        finally:
            _CALLER.reset(token)

    @abstractmethod
    def run(self, service: str, inputs: dict[str, Any]) -> dict[str, Any]: ...


class RecordingKernel(KernelServices):
    def __init__(self, results: dict[str, dict[str, Any]] | None = None):
        self.results = dict(results or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, service, inputs):
        self.calls.append((service, dict(inputs)))
        out = dict(self.results.get(service, {"ok": True}))
        if "id" in lookup(service).result and "id" not in out:
            out["id"] = f"{service}-{len(self.calls)}"     # a creating reply needs an id
        return out


class LocalKernel(KernelServices):
    def __init__(self, root: str | Path, workspace: Any = None, environment: Any = None,
                 harness_examples: int = 50, commits: Any = None, tlc_jar: Any = None):
        from ..commits import CommitStore
        self.root = Path(root).resolve()
        self.workspace = workspace          # toprope.workspace.Workspace: sources and the interview
        self.environment = environment      # toprope.deploy.LocalEnvironment, for preview and deploy
        self.examples = harness_examples
        self.commits = commits or CommitStore(self.root / ".toprope" / "commits")
        # A domain's own event log, by domain (ADR-0037): the self domains keep theirs in git,
        # so a change check replays their real history even with nothing deployed.
        self.domain_events: dict[str, Any] = {}
        # With a TLC jar, the change check model-checks too, and approval needs it passed (ADR-0043).
        self.tlc_jar = tlc_jar

    def _path(self, rel: str) -> Path:
        p = (self.root / str(rel)).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError(fixed(f"{rel} is outside the kernel's root", "give a path inside the repository the kernel runs on (`--kernel-root`)"))
        return p


    def _domain(self, declaration: str):
        from ..decl import load_domain
        return load_domain(self._path(declaration))

    def _validate(self, declaration):
        from ..decl import validate_domain
        issues = validate_domain(self._domain(declaration))
        errors = [i for i in issues if i.severity == "error"]
        return {"ok": not errors, "errors": len(errors), "warnings": len(issues) - len(errors),
                "summary": "; ".join(f"{i.code} at {i.where}" for i in errors[:3])}

    def _compile(self, declaration):
        from ..decl import interface, validate_domain
        d = self._domain(declaration)
        errors = [i for i in validate_domain(d) if i.severity == "error"]
        return {"ok": not errors, "objects": len(d.objects), "actions": len(d.actions),
                "elements": len(interface(d)), "summary": f"{len(errors)} error(s)" if errors else "compiled"}

    def _check_composition(self, composition):
        from ..compose import check_composition, load_composition
        issues = check_composition(load_composition(self._path(composition)))
        return {"ok": not issues, "issues": len(issues),
                "summary": "; ".join(f"{i.code} at {i.where}" for i in issues[:3])}

    def _run_harness(self, declaration):
        from ..harness import run_harness
        r = run_harness(self._domain(declaration), levels=("model", "execution"),
                        explore_examples=self.examples, races=False)
        c = r.coverage
        return {"ok": r.ok, "findings": len(r.findings), "cells_covered": c["cells"]["covered"].get("execution", 0),
                "unreachable": sum(len(v) for v in c["unreachable"].values()),
                "summary": r.summary().splitlines()[0]}

    def _world_map(self, declaration):
        from ..harness import grow_world
        from ..worldmap import build_world_map
        d = self._domain(declaration)
        m = build_world_map(d)
        return {"undecided": sum(e["fog"] for e in m["behavior"]["edges"]), "edges": len(m["behavior"]["edges"]),
                "unreachable": sum(len(v) for v in grow_world(d).unreachable.values())}

    def _read_source(self, source):
        if self.workspace is None:
            raise RuntimeError(fixed("no authoring workspace configured", "pass `--workspace` the workspace file, or set `workspace:` in toprope.yaml"))
        spec = self.workspace.sources.get(source)
        if spec is None:
            raise KeyError(fixed(f"no source {source!r}", "use a source id listed in the workspace file's `sources:`"))
        return {"chunks": len(self.workspace.chunks(source)), "local_only": spec.local_only}

    def _fetch_source(self, source):
        if self.workspace is None:
            raise RuntimeError(fixed("no authoring workspace configured", "pass `--workspace` the workspace file, or set `workspace:` in toprope.yaml"))
        (meta,) = self.workspace.fetch(source)
        return {"sha256": meta["sha256"]}

    # -- the interview (ADR-0025, ADR-0037) ------------------------------------------------------
    def _ws(self):
        if self.workspace is None:
            raise RuntimeError(fixed("no authoring workspace configured", "pass `--workspace` the workspace file, or set `workspace:` in toprope.yaml"))
        return self.workspace

    def _search_sources(self, query):
        return {"refs": [h["ref"] for h in self._ws().search_sources(query)]}

    def _stage_questions(self):
        q = self._ws().questions()
        texts = [x["text"] for x in q.get("questions", [])]
        # `text`: the bundle as one string, for a declaration to keep (a property holds no list).
        return {"stage": q.get("stage") or "", "bundle": q.get("bundle_id") or "",
                "questions": texts, "text": "\n".join(f"- {t}" for t in texts)}

    def _propose_element(self, path, value, source):
        import json
        out = self._ws().propose(path, json.loads(value), source)
        errors = [i for i in out["issues"] if i.get("severity") == "error"]
        return {"ok": not errors, "issues": len(errors), "summary": "; ".join(i["message"] for i in errors[:3])}

    def _record_answer(self, question, answer, decisions):
        import json
        chosen = (decisions or "").strip()            # `choice:<id>`: a ready answer (ADR-0049, B1)
        out = self._ws().answer(question, answer, chosen if chosen.startswith("choice:") else json.loads(chosen or "[]"),
                                question=question)
        return {"ref": out["ref"]}

    def _confirm_element(self, paths, approver):
        ws = self._ws()
        chosen = ws._proposed(ws.draft()) if paths.strip() == "all" else paths.split()
        if not chosen:
            raise ValueError(fixed("nothing to confirm: no paths given, or nothing is proposed", "propose elements first, or name the paths to confirm"))
        ws.confirm(chosen, via="kernel", who=approver)
        return {"confirmed": chosen}

    def _skip_stage(self, stage, reason):
        self._ws().skip_stage(stage, reason)
        return {"skipped": True}

    # -- commits (ADR-0029) -----------------------------------------------------------------
    def _commit(self, declaration):
        c, created = self.commits.commit(self._path(declaration), author=str((self.caller or {}).get("id") or ""))
        base = self.commits.review_base(c.domain, c.id)      # ADR-0033
        review = self.commits.diff(c.domain, base, c.id)["to_review"] if created else []
        approved = self.commits.latest_approved(c.domain)
        return {"id": c.id, "seq": c.seq, "content": c.content, "created": created,
                "parent": c.parents[0] if c.parents else "", "interface": c.interface, "to_review": review,
                "last_approved": approved.id if approved else "", "domain": c.domain, "branch": c.branch,
                "author": c.author}

    def _cite_evidence(self, domain, commit, kind, ref):
        if kind in ("interview", "source"):
            ref = self._ws().resolve_ref(ref)[0]             # words from the passage resolve (B4)
            spec = self._ws().sources.get(ref.split(":", 1)[0])
            if spec is not None and (spec.kind == "interview-log") != (kind == "interview"):
                raise ValueError(fixed(f"{ref} is {'an interview line' if spec.kind == 'interview-log' else 'a source chunk'}:"
                                 f" not a {kind}", f"cite it with `--kind {'interview' if spec.kind == 'interview-log' else 'source'}`"))
        elif kind == "event":
            stream, _, version = ref.rpartition("@")
            if self.environment is None:
                raise RuntimeError(fixed("no deploy environment configured: no events to cite", "pass `--env` the local deploy environment, or set `env:` in toprope.yaml"))
            with self.environment.events(domain) as store:
                if store is None:
                    raise RuntimeError(fixed(f"{domain} is not deployed here: no events to cite", "deploy it here first, or cite another kind of evidence"))
                if not stream or not version.isdigit() or not 1 <= int(version) <= store.version(stream):
                    raise ValueError(fixed(f"no event {ref!r} in the deployed domain's event log", "give `<stream>@<version>`: an object's id and the version of one of its events there"))
        elif kind == "approval-run":
            self._approval_run(ref)
        e = self.commits.cite(domain, commit, kind, ref, by=str((self.caller or {}).get("id") or ""))
        return {"strength": e["strength"]}

    def _approval_run(self, url):
        """A GitHub Actions run that approved a human request (ADR-0039). The workflow records
        each approved run in `.toprope/approval-runs.jsonl` with the result it pushes, so the
        record survives a squash merge."""
        import json
        log = self.root / APPROVAL_RUNS
        runs = [json.loads(x) for x in log.read_text().splitlines() if x.strip()] if log.exists() else []
        entries = [r for r in runs if r.get("run") == url]
        if not entries:
            raise ValueError(fixed(f"no approved human request ran as {url!r} ({APPROVAL_RUNS})", "cite the run URL of an approved human request, as `.toprope/approval-runs.jsonl` lists it"))
        for r in entries:   # a run that failed at or before an approval step did not approve
            failed = (r.get("failed") or {}).get("step")
            if failed and any((st.get("run") or {}).get("action") == "approve_commit"
                              for st in (r.get("steps") or [])[failed - 1:]):
                raise ValueError(fixed(f"the human request run {url!r} failed at step {failed}, at or before its approve_commit step, so it approved nothing", "cite the run of the request that approved the commit (the rest of this one, once it ran)"))

    def run(self, service, inputs):
        if service == "diff":   # `from` is a Python keyword
            return self.commits.diff(inputs["domain"], inputs["from"] or None, inputs["to"])
        return getattr(self, f"_{service}")(**inputs)

    def _approve_commit(self, domain, commit, approver):
        if self.tlc_jar:
            tla = self.commits.check_status(domain, commit).get("tla") or {}
            if tla.get("ok") is not True:
                raise ValueError(fixed(f"{commit} has no passing TLC check ({tla.get('summary') or 'never run with TLC'})", "run `check_commit` here, where TLC is configured (TOPROPE_TLC_JAR), then approve"))
        self.commits.approve(domain, commit, approver)   # conflicts fail the call, as any error does
        return {"approved": True, "main": self.commits.main(domain).id}

    def _change_check(self, domain, commit):
        from ..check import check_commit
        from ..check.nl_llm import from_env
        from ..incremental import ResultCache
        rc = ResultCache(self.root / ".toprope" / "cache")
        nl = from_env()                                  # TOPROPE_NL_COMMAND: the natural-language check
        own = self.domain_events.get(domain)
        if own is not None:
            r = check_commit(self.commits, domain, commit, events=own, examples=self.examples, cache=rc, nl=nl,
                             tlc=self.tlc_jar)
        elif self.environment is not None:
            with self.environment.events(domain) as store:
                r = check_commit(self.commits, domain, commit, events=store, examples=self.examples, cache=rc, nl=nl,
                                 tlc=self.tlc_jar)
        else:
            r = check_commit(self.commits, domain, commit, examples=self.examples, cache=rc, nl=nl, tlc=self.tlc_jar)
        from ..decl.provenance import proposed_elements
        left = proposed_elements(self.commits.declaration(domain, commit))
        failing = [n for n, c in r.checks.items() if not c.ok] + (["confirmed"] if left else [])
        summary = r.summary() + (f"; {len(left)} proposed element(s) to confirm" if left else "")
        return {"passed": r.ok and not left, "errors": r.errors, "warnings": r.warnings,   # ADR-0041
                "failing": failing, "summary": summary}

    def _merge_main(self, domain, branch, declaration):
        from ..decl.yamlio import load_yaml
        path = self._path(declaration)
        out = self.commits.merge_main(domain, path, branch, (load_yaml(path.read_text()) or {}).get("version", 1))
        return {"merge": out["merge"], "up_to_date": out["up_to_date"], "conflicts": len(out["conflicts"]),
                "paths": [c["path"] for c in out["conflicts"]]}

    def _checkout(self, domain, commit, declaration):
        c = self.commits.checkout(domain, commit, self._path(declaration))
        return {"content": c.content}

    def _preview(self, domain, commit):
        if self.environment is None:
            raise RuntimeError(fixed("no deploy environment configured", "pass `--env` the local deploy environment, or set `env:` in toprope.yaml"))
        b = self.environment.preview_commit(self.commits, domain, commit, examples=self.examples)
        return {"ok": b.harness_ok, "build": b.id, "harness_ok": b.harness_ok}

    def _deploy(self, domain, commit, approver):
        from ..deploy import DeployRefused
        from ..types import Actor
        if self.environment is None:
            raise RuntimeError(fixed("no deploy environment configured", "pass `--env` the local deploy environment, or set `env:` in toprope.yaml"))
        try:
            self.environment.deploy_commit(self.commits, domain, commit, Actor(approver, "person"))
        except DeployRefused as e:
            return {"ok": False, "deployed": False, "error": f"{e.rule}: {e.reason}"}
        return {"deployed": True}

    def _probe(self, domain, commit):
        if self.environment is None:
            raise RuntimeError(fixed("no deploy environment configured", "pass `--env` the local deploy environment, or set `env:` in toprope.yaml"))
        return self.environment.probe_commit(self.commits, domain, commit, events=self.domain_events.get(domain))


__all__ = ["KernelServices", "LocalKernel", "RecordingKernel", "complete"]
