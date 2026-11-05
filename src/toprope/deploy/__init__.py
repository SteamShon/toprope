"""The local deploy adapter (roadmap M0a item 14, ADR-0022): preview → deploy to a local
environment, so the M1 Delivery domain has real effects to model.

An environment is a directory:
  builds/<build id>/   domain.yaml, harness.json, world-map.json, build.json
  current.json         the deployed build (replaced atomically)
  deployments.jsonl    every deploy and refusal, append-only
  events.db            the deployed domain's event store (serve it with `server_args()`)

**The fixed floor.** `deploy` enforces, in code, rules no declaration can weaken (ADR-0022):
1. the build's declaration is unchanged since preview (its hash), and the toolchain that
   ran the harness is the current one (no taint)
2. the harness passed for that build
3. a person approves: never an agent or the system
4. no object in the environment would be stranded (a type or state the new declaration
   lacks). Migration plans come in M0b, so a stranding deploy is refused.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..decl import Domain, load_yaml, validate_domain
from ..types import Actor

PACKAGE = Path(__file__).resolve().parents[1]


class DeployRefused(Exception):
    def __init__(self, rule: str, reason: str):
        super().__init__(f"{rule}: {reason}")
        self.rule, self.reason = rule, reason


def toolchain_hash() -> str:
    """The hand-built kernel's source (ADR-0013): a harness result is valid only for it."""
    h = hashlib.sha256()
    for p in sorted(PACKAGE.rglob("*.py")):
        h.update(p.relative_to(PACKAGE).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_atomic(path: Path, text: str) -> None:
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")   # unique per writer
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


@dataclass(frozen=True)
class Build:
    id: str
    domain: str
    version: int
    declaration_sha256: str
    toolchain: str
    harness_ok: bool
    created_at: str


class LocalEnvironment:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def store_path(self) -> Path:
        return self.root / "events.db"

    # -- preview ---------------------------------------------------------------------------
    def preview(self, declaration: str | Path, levels: tuple[str, ...] = ("model", "execution"),
                examples: int = 100) -> Build:
        """Build the artifacts and run the harness. The build id is the declaration's hash."""
        from ..harness import run_harness
        from ..worldmap import build_world_map
        raw = Path(declaration).read_bytes()
        d = Domain.model_validate(load_yaml(raw.decode()))
        errors = [i for i in validate_domain(d) if i.severity == "error"]
        report = None if errors else run_harness(d, levels=levels, explore_examples=examples, races=False)
        sha = _sha(raw)
        build = Build(sha[:16], d.domain, d.version, sha, toolchain_hash(),
                      bool(report and report.ok), _now())
        out = self.root / "builds" / build.id
        out.mkdir(parents=True, exist_ok=True)
        (out / "domain.yaml").write_bytes(raw)
        harness = report.to_json() if report else {"ok": False, "errors": [i.__dict__ for i in errors]}
        (out / "harness.json").write_text(json.dumps(harness, indent=2, default=str))
        (out / "world-map.json").write_text(json.dumps(build_world_map(d, report.to_json() if report else None),
                                                       indent=2, sort_keys=True))
        (out / "build.json").write_text(json.dumps(asdict(build), indent=2))
        return build

    def build(self, build_id: str) -> Build | None:
        p = self.root / "builds" / build_id / "build.json"
        return Build(**json.loads(p.read_text())) if p.exists() else None

    @contextmanager
    def _lock(self):
        """One deploy at a time per environment (ADR-0029): the ref moves under a lock."""
        with open(self.root / ".lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    # -- commits (ADR-0029) -------------------------------------------------------------------
    def preview_commit(self, commits: Any, domain: str, commit_id: str, levels: tuple[str, ...] = ("model", "execution"),
                       examples: int = 100) -> Build:
        """Build a commit from the commit store; `commit.json` in the build links it to the commit."""
        c = commits.get(domain, commit_id)
        src = self.root / "builds" / ".incoming" / f"{c.content}.domain.yaml"
        src.parent.mkdir(parents=True, exist_ok=True)
        commits.export(domain, commit_id, src)
        b = self.preview(src, levels=levels, examples=examples)
        meta = {**asdict(b), "commit": c.id, "seq": c.seq, "commit_domain": domain}
        (self.root / "builds" / b.id / "commit.json").write_text(json.dumps(meta, indent=2))
        return b

    def deploy_commit(self, commits: Any, domain: str, commit_id: str, approver: Actor) -> dict[str, Any]:
        """Point this environment at a commit. Besides the build floor, the commit must be
        approved, must not be superseded by a newer approved commit, and must be newer than the
        deployed one: no downgrades without an explicit rollback (M2)."""
        c = commits.get(domain, commit_id)
        with self._lock():
            build_id = next((p.parent.name for p in (self.root / "builds").glob("*/commit.json")
                             if json.loads(p.read_text())["commit"] == c.id), None)
            try:
                if not commits.is_approved(domain, c.id):
                    raise DeployRefused("unapproved", f"commit {c.id} has no approval")
                latest = commits.latest_approved(domain)
                if latest is not None and latest.seq > c.seq:
                    raise DeployRefused("superseded", f"commit {c.id} is superseded by approved {latest.id}")
                cur = self.current()
                if cur and cur.get("commit_domain") == domain and cur.get("seq", 0) >= c.seq:
                    raise DeployRefused("downgrade", f"{cur.get('commit')} is deployed; {c.id} is not newer "
                                                     "(rollback comes in M2)")
                if build_id is None:
                    raise DeployRefused("no-build", f"commit {c.id} has not been previewed")
            except DeployRefused as e:
                self._log({"at": _now(), "commit": c.id, "result": "refused", "rule": e.rule,
                           "reason": e.reason, "approver": approver.ref()})
                raise
            return self._deploy_locked(build_id, approver, {"commit": c.id, "seq": c.seq, "commit_domain": domain})

    # -- deploy (the fixed floor) ------------------------------------------------------------
    def deploy(self, build_id: str, approver: Actor) -> dict[str, Any]:
        with self._lock():
            return self._deploy_locked(build_id, approver, {})

    def _deploy_locked(self, build_id: str, approver: Actor, extra: dict[str, Any]) -> dict[str, Any]:
        try:
            build = self._floor(build_id, approver)
        except DeployRefused as e:
            self._log({"at": _now(), "build": build_id, "result": "refused", "rule": e.rule,
                       "reason": e.reason, "approver": approver.ref()})
            raise
        current = {"build": build.id, "domain": build.domain, "version": build.version,
                   "declaration": str(self.root / "builds" / build.id / "domain.yaml"),
                   "deployed_at": _now(), "approver": approver.ref(), **extra}
        _write_atomic(self.root / "current.json", json.dumps(current, indent=2))
        self._log({"at": current["deployed_at"], "build": build.id, "result": "deployed", "approver": approver.ref()})
        return current

    def _floor(self, build_id: str, approver: Actor) -> Build:
        build = self.build(build_id)
        if build is None:
            raise DeployRefused("no-build", f"no build {build_id}; run preview first")
        decl = (self.root / "builds" / build_id / "domain.yaml").read_bytes()
        if _sha(decl) != build.declaration_sha256:
            raise DeployRefused("tainted", "the build's declaration changed after preview")
        if build.toolchain != toolchain_hash():
            raise DeployRefused("tainted", "the toolchain changed since the harness ran; preview again")
        if not build.harness_ok:
            raise DeployRefused("harness", "the harness did not pass for this build")
        if approver.kind != "person":
            raise DeployRefused("approver", "a person approves a deploy, never an agent or the system")
        stranded = self.stranded(Domain.model_validate(load_yaml(decl.decode())))
        if stranded:
            raise DeployRefused("stranded", f"{len(stranded)} object(s) would be stranded: "
                                + ", ".join(stranded[:5]) + " (migration plans come in M0b)")
        return build

    def stranded(self, d: Domain) -> list[str]:
        """Objects in this environment whose type, or state, the new declaration lacks."""
        if not self.store_path.exists():
            return []
        from ..semantics.model import project
        from ..store.sqlite import SQLiteEventStore
        store = SQLiteEventStore(str(self.store_path))
        try:
            out = []
            for stream in store.streams():
                evs = store.read(stream)
                if not evs or evs[0].kind != "domain":
                    continue
                obj, st = evs[0].aggregate, project(evs) or {}
                if obj not in d.objects:
                    out.append(f"{stream} ({obj} is gone)")
                    continue
                tr = d.transitions.get(obj)
                if tr is not None and st.get(tr.field) not in tr.matrix:
                    out.append(f"{stream} (state {st.get(tr.field)!r} is gone)")
            return out
        finally:
            store.close()

    # -- status ------------------------------------------------------------------------------
    def current(self) -> dict[str, Any] | None:
        p = self.root / "current.json"
        return json.loads(p.read_text()) if p.exists() else None

    def history(self) -> list[dict[str, Any]]:
        p = self.root / "deployments.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []

    def server_args(self) -> list[str]:
        cur = self.current()
        if cur is None:
            raise DeployRefused("no-deploy", "nothing is deployed in this environment")
        return ["--domain", cur["declaration"], "--store", f"sqlite:{self.store_path}"]

    def _log(self, entry: dict[str, Any]) -> None:
        with (self.root / "deployments.jsonl").open("a") as f:
            f.write(json.dumps(entry) + "\n")


__all__ = ["Build", "DeployRefused", "LocalEnvironment", "toolchain_hash"]
