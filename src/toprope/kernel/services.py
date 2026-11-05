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

from . import CATALOG, Service


def complete(svc: Service, result: dict[str, Any]) -> dict[str, Any]:
    """Every field, always (ADR-0028): defaults for what a result leaves out."""
    full = {**svc.failure(""), **{k: v for k, v in result.items() if k in svc.fields()}}
    full["ok"] = bool(result.get("ok", True))
    full["error"] = str(result.get("error") or "")
    return full


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
        svc = CATALOG.get(service)
        if svc is None:
            raise KeyError(f"no kernel service {service!r}")
        missing = [i for i in svc.inputs if i not in inputs]
        if missing:
            return svc.failure(f"missing inputs {missing}")
        if "approver" in svc.inputs:
            if not caller or caller.get("kind") != "person" or caller.get("id") != inputs["approver"]:
                return svc.failure(f"{service} records a person's decision: the calling person must be the approver")
        token = _CALLER.set(caller)
        try:
            return complete(svc, self.run(service, {k: inputs[k] for k in svc.inputs}))
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
        if "id" in CATALOG[service].result and "id" not in out:
            out["id"] = f"{service}-{len(self.calls)}"     # a creating reply needs an id
        return out


class LocalKernel(KernelServices):
    def __init__(self, root: str | Path, workspace: Any = None, environment: Any = None,
                 harness_examples: int = 50, commits: Any = None):
        from ..commits import CommitStore
        self.root = Path(root).resolve()
        self.workspace = workspace          # toprope.authoring.Workspace, for sources
        self.environment = environment      # toprope.deploy.LocalEnvironment, for preview and deploy
        self.examples = harness_examples
        self.commits = commits or CommitStore(self.root / ".toprope" / "commits")

    def _path(self, rel: str) -> Path:
        p = (self.root / str(rel)).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError(f"{rel} is outside the kernel's root")
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
            raise RuntimeError("no authoring workspace configured")
        spec = self.workspace.sources.get(source)
        if spec is None:
            raise KeyError(f"no source {source!r}")
        return {"chunks": len(self.workspace.chunks(source)), "local_only": spec.local_only}

    def _fetch_source(self, source):
        if self.workspace is None:
            raise RuntimeError("no authoring workspace configured")
        (meta,) = self.workspace.fetch(source)
        return {"sha256": meta["sha256"]}

    # -- commits (ADR-0029) -----------------------------------------------------------------
    def _commit(self, declaration):
        c, created = self.commits.commit(self._path(declaration), author=str((self.caller or {}).get("id") or ""))
        main = self.commits.main(c.domain)          # reviewed from the merge base with main (ADR-0033)
        base = self.commits.merge_base(c.domain, c.id, main.id) if main else None
        review = self.commits.diff(c.domain, base, c.id)["to_review"] if created else []
        approved = self.commits.latest_approved(c.domain)
        return {"id": c.id, "seq": c.seq, "content": c.content, "created": created,
                "parent": c.parents[0] if c.parents else "", "interface": c.interface, "to_review": review,
                "last_approved": approved.id if approved else ""}

    def run(self, service, inputs):
        if service == "diff":   # `from` is a Python keyword
            return self.commits.diff(inputs["domain"], inputs["from"] or None, inputs["to"])
        return getattr(self, f"_{service}")(**inputs)

    def _approve_commit(self, domain, commit, approver):
        self.commits.approve(domain, commit, approver)   # conflicts fail the call, as any error does
        return {"approved": True, "main": self.commits.main(domain).id}

    def _change_check(self, domain, commit):
        from ..check import check_commit
        if self.environment is not None:
            with self.environment.events() as store:
                r = check_commit(self.commits, domain, commit, events=store, examples=self.examples)
        else:
            r = check_commit(self.commits, domain, commit, examples=self.examples)
        return {"passed": r.ok, "errors": r.errors, "warnings": r.warnings,
                "failing": [n for n, c in r.checks.items() if not c.ok], "summary": r.summary()}

    def _checkout(self, domain, commit, declaration):
        c = self.commits.checkout(domain, commit, self._path(declaration))
        return {"content": c.content}

    def _preview(self, domain, commit):
        if self.environment is None:
            raise RuntimeError("no deploy environment configured")
        b = self.environment.preview_commit(self.commits, domain, commit, examples=self.examples)
        return {"ok": b.harness_ok, "build": b.id, "harness_ok": b.harness_ok}

    def _deploy(self, domain, commit, approver):
        from ..deploy import DeployRefused
        from ..types import Actor
        if self.environment is None:
            raise RuntimeError("no deploy environment configured")
        try:
            self.environment.deploy_commit(self.commits, domain, commit, Actor(approver, "person"))
        except DeployRefused as e:
            return {"ok": False, "deployed": False, "error": f"{e.rule}: {e.reason}"}
        return {"deployed": True}


__all__ = ["KernelServices", "LocalKernel", "RecordingKernel", "complete"]
