"""The commit store (ADR-0029): Authoring as an immutable commit log, Delivery as a ref.

Layout under `<root>/<domain>/`:
  objects/<content>/domain.yaml       the declaration without `version`, stored once per content
  objects/<content>/representations/  its representations, if any (a released UI is the pair)
  log.jsonl                           one line per commit: id, seq, content, parents, at, interface
  approvals.jsonl                     one line per approval: commit, approver, at (never removed)

- **Content-addressed.** `content` is the hash of the canonical declaration without
  `version`, plus its representations. A commit's id is `<seq>-<content>`. Reading a commit
  sets `version` to its sequence number. Committing content identical to the head makes no
  new commit; returning to an earlier content makes a new commit that shares its object.
- **Append-only.** Nothing is rewritten. A wrong approval is superseded by approving a newer
  commit.
- **Parents are a list**, one parent in M1, so merge commits can come later without
  migration.
- **One writer at a time** per domain (a file lock).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..decl import Domain, diff_interface, interface, load_yaml, review_diff, review_elements


class CommitError(Exception):
    pass


@dataclass(frozen=True)
class Commit:
    id: str                      # <seq>-<content>
    seq: int
    domain: str
    content: str                 # the content hash: the object, and the build id when deployed
    parents: list[str] = field(default_factory=list)
    at: str = ""
    interface: str = "1.0.0"     # the derived interface version (ADR-0008)
    message: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def content_id(declaration: dict[str, Any], representations: dict[str, Any] | None = None) -> str:
    body = {k: v for k, v in declaration.items() if k != "version"}
    return hashlib.sha256(_canon({"domain": body, "representations": representations or {}}).encode()).hexdigest()[:16]


def _bump(version: str, kind: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return version


class CommitStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    # -- paths and locking --------------------------------------------------------------------
    def _dir(self, domain: str) -> Path:
        d = (self.root / domain).resolve()
        if not d.is_relative_to(self.root):
            raise CommitError(f"bad domain name {domain!r}")
        return d

    @contextmanager
    def _lock(self, domain: str):
        d = self._dir(domain)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / ".lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield d
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def _append(path: Path, entry: dict[str, Any]) -> None:
        with open(path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

    @staticmethod
    def _lines(path: Path) -> list[dict[str, Any]]:
        return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []

    # -- reading ----------------------------------------------------------------------------------
    def log(self, domain: str) -> list[Commit]:
        return [Commit(**c) for c in self._lines(self._dir(domain) / "log.jsonl")]

    def head(self, domain: str) -> Commit | None:
        log = self.log(domain)
        return log[-1] if log else None

    def get(self, domain: str, commit_id: str) -> Commit:
        c = next((c for c in self.log(domain) if c.id == commit_id), None)
        if c is None:
            raise CommitError(f"no commit {commit_id} in {domain}")
        return c

    def declaration(self, domain: str, commit_id: str) -> dict[str, Any]:
        """The commit's declaration, with `version` set to its sequence number."""
        c = self.get(domain, commit_id)
        raw = load_yaml((self._dir(domain) / "objects" / c.content / "domain.yaml").read_text())
        return {**raw, "version": c.seq}

    def domain(self, domain: str, commit_id: str) -> Domain:
        return Domain.model_validate(self.declaration(domain, commit_id))

    def export(self, domain: str, commit_id: str, out: str | Path) -> Path:
        """Write the commit's declaration (with its version) to a file, e.g. for a build."""
        p = Path(out)
        p.write_text(yaml.safe_dump(self.declaration(domain, commit_id), sort_keys=False, allow_unicode=True))
        return p

    def approvals(self, domain: str) -> list[dict[str, Any]]:
        return self._lines(self._dir(domain) / "approvals.jsonl")

    def is_approved(self, domain: str, commit_id: str) -> bool:
        return any(a["commit"] == commit_id for a in self.approvals(domain))

    def latest_approved(self, domain: str) -> Commit | None:
        approved = {a["commit"] for a in self.approvals(domain)}
        cs = [c for c in self.log(domain) if c.id in approved]
        return max(cs, key=lambda c: c.seq) if cs else None

    # -- writing ----------------------------------------------------------------------------------
    def commit(self, declaration: str | Path, representations: list[str | Path] | None = None,
               message: str = "") -> tuple[Commit, bool]:
        """Snapshot a working copy. Returns (commit, created). Identical content to the head
        returns the head, created False."""
        raw = load_yaml(Path(declaration).read_text()) or {}
        d = Domain.model_validate(raw)
        if representations is None:   # a released UI is the pair (ADR-0008): take this domain's own
            representations = self.representations_for(d.domain, Path(declaration).parent)
        reps = {Path(r).name: load_yaml(Path(r).read_text()) for r in representations}
        cid = content_id(raw, reps)
        with self._lock(d.domain) as dirp:
            log = self.log(d.domain)
            head = log[-1] if log else None
            if head is not None and head.content == cid:
                return head, False
            seq = (head.seq if head else 0) + 1
            iface = "1.0.0"
            if head is not None:
                old = interface(self.domain(d.domain, head.id))
                iface = _bump(head.interface, diff_interface(old, interface(d)).bump)
            c = Commit(f"{seq}-{cid}", seq, d.domain, cid, [head.id] if head else [], _now(), iface, message)
            obj = dirp / "objects" / cid
            if not obj.exists():
                tmp = Path(tempfile.mkdtemp(dir=dirp, prefix=".obj-"))
                body = {k: v for k, v in raw.items() if k != "version"}
                (tmp / "domain.yaml").write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))
                if reps:
                    (tmp / "representations").mkdir()
                    for name, rbody in reps.items():
                        (tmp / "representations" / name).write_text(yaml.safe_dump(rbody, sort_keys=False))
                (dirp / "objects").mkdir(exist_ok=True)
                os.replace(tmp, obj)
            self._append(dirp / "log.jsonl", asdict(c))
            return c, True

    @staticmethod
    def representations_for(domain: str, folder: Path) -> list[Path]:
        """The `*.representation.yaml` files next to a declaration that target its domain. A file
        that cannot be read is an error, never skipped: a release would silently lose its UI."""
        out = []
        for p in sorted(folder.glob("*.representation.yaml")):
            try:
                body = load_yaml(p.read_text()) or {}
            except Exception as e:
                raise CommitError(f"cannot read {p.name}: {e}") from None
            if isinstance(body, dict) and (body.get("targets") or {}).get("domain") == domain:
                out.append(p)
        return out

    def approve(self, domain: str, commit_id: str, approver: str) -> bool:
        """Tag a commit as approved. Immutable; approving it again is a no-op (False)."""
        with self._lock(domain) as dirp:
            self.get(domain, commit_id)
            if self.is_approved(domain, commit_id):
                return False
            self._append(dirp / "approvals.jsonl", {"commit": commit_id, "approver": approver, "at": _now()})
            return True

    # -- the semantic diff ------------------------------------------------------------------------
    def diff(self, domain: str, a: str | None, b: str) -> dict[str, Any]:
        """Elements of `b` that changed directly since `a` (None: since nothing). The owner
        re-confirms `to_review`; indirect effects are the change check's to report."""
        new = review_elements(self.domain(domain, b))
        old = review_elements(self.domain(domain, a)) if a else {}
        r = review_diff(old, new)
        return {"changed": r.changed, "added": r.added, "removed": r.removed, "to_review": r.to_review}


__all__ = ["Commit", "CommitError", "CommitStore", "content_id"]
