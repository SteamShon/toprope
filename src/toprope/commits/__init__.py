"""The commit store (ADR-0029): Authoring as an immutable commit log, Delivery as a ref.

Layout under `<root>/<domain>/`:
  objects/<content>/domain.yaml       the declaration without `version`, stored once per content
  objects/<content>/representations/  its representations, if any (a released UI is the pair)
  log.jsonl                           one line per commit: id, seq, content, parents, at, interface
  refs.jsonl                          one line per ref move: branch, commit, at (ADR-0033)
  approvals.jsonl                     one line per approval: commit, approver, at (never removed)

- **Content-addressed.** `content` is the hash of the canonical declaration without
  `version`, plus its representations. A commit's id is `<seq>-<content>`. Reading a commit
  sets `version` to its sequence number. Committing content identical to the head makes no
  new commit; returning to an earlier content makes a new commit that shares its object.
- **Append-only.** Nothing is rewritten. A wrong approval is superseded by approving a newer
  commit.
- **Branches** (ADR-0033). A branch is a named ref to a commit; a commit goes onto a branch
  (`work` by default), starting from `main` when the branch is new. `main` is protected:
  only `approve` moves it, so approving means merging into `main` (fast-forward, or a merge
  commit with two parents) and tagging what `main` then points to.
- **Merge is semantic.** A 3-way merge from the nearest common ancestor, per declaration path:
  a path changed on one side takes that side, a path changed differently on both sides is a
  conflict. Conflicts are resolved in a working copy and committed with `merge=` (a second
  parent); the merge result must validate.
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
from pydantic import ValidationError

from ..decl import (
    Domain,
    diff_interface,
    interface,
    load_yaml,
    review_diff,
    review_elements,
    validate_domain,
)

MAIN = "main"
DEFAULT_BRANCH = "work"


class CommitError(Exception):
    pass


@dataclass(frozen=True)
class Conflict:
    path: str                    # dotted path in the declaration (`representations.<file>...` for a UI)
    base: Any
    ours: Any
    theirs: Any


class MergeConflict(CommitError):
    def __init__(self, conflicts: list[Conflict]):
        self.conflicts = conflicts
        super().__init__("merge conflicts at " + ", ".join(c.path for c in conflicts))


@dataclass(frozen=True)
class Merge:
    base: str | None             # the merge base commit
    merged: dict[str, Any]       # {"domain": ..., "representations": ...}; ours at each conflict
    conflicts: list[Conflict]


_MISSING = object()


def _merge3(base: Any, ours: Any, theirs: Any, path: str, out: list[Conflict]) -> Any:
    if ours == theirs:
        return ours
    if base == ours:
        return theirs
    if base == theirs:
        return ours
    if all(isinstance(x, dict) or x is _MISSING for x in (base, ours, theirs)) \
            and isinstance(ours, dict) and isinstance(theirs, dict):
        b = base if isinstance(base, dict) else {}
        merged: dict[str, Any] = {}
        for k in list(ours) + [k for k in theirs if k not in ours] + [k for k in b if k not in ours and k not in theirs]:
            v = _merge3(b.get(k, _MISSING), ours.get(k, _MISSING), theirs.get(k, _MISSING), f"{path}.{k}" if path else str(k), out)
            if v is not _MISSING:
                merged[k] = v
        return merged
    def keyed(x: Any) -> bool:                       # a list of elements with ids: scenarios, invariants
        return isinstance(x, list) and all(isinstance(e, dict) and "id" in e for e in x)

    def scalars(x: Any) -> bool:                     # a list of names: roles
        return isinstance(x, list) and all(isinstance(e, (str, int, float, bool)) for e in x)

    if keyed(ours) and keyed(theirs) and (base is _MISSING or keyed(base)):
        def as_map(x: Any) -> dict[str, Any]:
            return {e["id"]: e for e in x} if isinstance(x, list) else {}
        return list(_merge3(as_map(base), as_map(ours), as_map(theirs), path, out).values())
    if scalars(ours) and scalars(theirs) and (base is _MISSING or scalars(base)):
        b = base if isinstance(base, list) else []
        gone = {e for e in b if e not in ours or e not in theirs}        # removed on either side
        return [e for e in dict.fromkeys(ours + theirs) if e not in gone]
    out.append(Conflict(path, None if base is _MISSING else base, None if ours is _MISSING else ours,
                        None if theirs is _MISSING else theirs))
    return ours


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
    branch: str = ""             # the branch it was made on (for reading; refs decide heads)


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

    def refs(self, domain: str) -> dict[str, str]:
        """Every branch → the commit it points to. `main` is absent until the first approval."""
        out: dict[str, str] = {}
        for r in self._lines(self._dir(domain) / "refs.jsonl"):
            out[r["branch"]] = r["commit"]
        return out

    def head(self, domain: str, branch: str = DEFAULT_BRANCH) -> Commit | None:
        cid = self.refs(domain).get(branch)
        return self.get(domain, cid) if cid else None

    def main(self, domain: str) -> Commit | None:
        return self.head(domain, MAIN)

    def ancestors(self, domain: str, commit_id: str) -> set[str]:
        """The commit and everything it descends from."""
        by_id = {c.id: c for c in self.log(domain)}
        seen, todo = set(), [commit_id]
        while todo:
            c = todo.pop()
            if c not in seen and c in by_id:
                seen.add(c)
                todo.extend(by_id[c].parents)
        return seen

    def is_ancestor(self, domain: str, a: str, b: str) -> bool:
        """True if `a` is `b` or an ancestor of `b`."""
        return a in self.ancestors(domain, b)

    def merge_base(self, domain: str, a: str, b: str) -> str | None:
        """The nearest common ancestor: a common ancestor no other common ancestor descends from."""
        common = self.ancestors(domain, a) & self.ancestors(domain, b)
        best = [c for c in common if not any(c != o and c in self.ancestors(domain, o) for o in common)]
        return max(best, key=lambda c: self.get(domain, c).seq) if best else None

    def get(self, domain: str, commit_id: str) -> Commit:
        c = next((c for c in self.log(domain) if c.id == commit_id), None)
        if c is None:
            raise CommitError(f"no commit {commit_id} in {domain}")
        return c

    def _body(self, domain: str, commit_id: str | None) -> dict[str, Any]:
        """The stored content of a commit: its declaration (no `version`) and representations."""
        if commit_id is None:
            return {"domain": {}, "representations": {}}
        obj = self._dir(domain) / "objects" / self.get(domain, commit_id).content
        reps = {p.name: load_yaml(p.read_text()) for p in sorted((obj / "representations").glob("*"))} \
            if (obj / "representations").exists() else {}
        return {"domain": load_yaml((obj / "domain.yaml").read_text()) or {}, "representations": reps}

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
        """What `main` points to. Only `approve` moves `main`, and it tags what it moves to."""
        return self.main(domain)

    def merge3(self, domain: str, ours: str, theirs: str) -> Merge:
        """The semantic 3-way merge of `theirs` into `ours`, from their merge base."""
        base = self.merge_base(domain, ours, theirs)
        conflicts: list[Conflict] = []
        merged = _merge3(self._body(domain, base), self._body(domain, ours), self._body(domain, theirs), "", conflicts)
        return Merge(base, merged, conflicts)

    # -- writing ----------------------------------------------------------------------------------
    def commit(self, declaration: str | Path, representations: list[str | Path] | None = None,
               message: str = "", branch: str = DEFAULT_BRANCH, merge: str | None = None) -> tuple[Commit, bool]:
        """Snapshot a working copy onto a branch. Returns (commit, created). A new branch starts
        from `main`. Identical content to the branch head returns the head, created False.
        `merge` names a second parent: the commit whose conflicts this working copy resolves."""
        if branch == MAIN:
            raise CommitError("`main` is protected: commit to a branch, and approving merges it into main")
        raw = load_yaml(Path(declaration).read_text()) or {}
        d = Domain.model_validate(raw)
        if representations is None:   # a released UI is the pair (ADR-0008): take this domain's own
            representations = self.representations_for(d.domain, Path(declaration).parent)
        reps = {Path(r).name: load_yaml(Path(r).read_text()) for r in representations}
        with self._lock(d.domain) as dirp:
            head = self.head(d.domain, branch) or self.main(d.domain)
            if merge is not None:
                self.get(d.domain, merge)
                if head is not None and self.is_ancestor(d.domain, merge, head.id):
                    merge = None                       # already merged: an ordinary commit
            if head is not None and merge is None and head.content == content_id(raw, reps):
                if self.refs(d.domain).get(branch) != head.id:
                    self._move(dirp, branch, head.id)
                return head, False
            parents = ([head.id] if head else []) + ([merge] if merge else [])
            return self._write(dirp, d.domain, raw, reps, parents, message, branch), True

    def _write(self, dirp: Path, domain: str, raw: dict[str, Any], reps: dict[str, Any], parents: list[str],
               message: str, branch: str) -> Commit:
        """Store a commit and move `branch` to it. Called under the domain lock."""
        d = Domain.model_validate({"version": 1, **raw})          # a stored body has no `version`
        cid = content_id(raw, reps)
        seq = max((c.seq for c in self.log(domain)), default=0) + 1
        iface = "1.0.0"
        if parents:
            first = self.get(domain, parents[0])
            iface = _bump(first.interface, diff_interface(interface(self.domain(domain, first.id)), interface(d)).bump)
        c = Commit(f"{seq}-{cid}", seq, domain, cid, parents, _now(), iface, message, branch)
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
        self._move(dirp, branch, c.id)
        return c

    def _move(self, dirp: Path, branch: str, commit_id: str) -> None:
        self._append(dirp / "refs.jsonl", {"branch": branch, "commit": commit_id, "at": _now()})

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

    def approve(self, domain: str, commit_id: str, approver: str) -> Commit | None:
        """Merge a commit into `main` and tag what `main` then points to (ADR-0033). Returns the
        approved commit: the commit itself on a fast-forward, or a new merge commit. Approving
        an approved commit again is a no-op (None). Raises MergeConflict on conflicts, and
        CommitError for a commit `main` already contains (approve a newer one instead)."""
        with self._lock(domain) as dirp:
            c = self.get(domain, commit_id)
            if self.is_approved(domain, c.id):
                return None
            main = self.main(domain)
            if main is not None and self.is_ancestor(domain, c.id, main.id):
                raise CommitError(f"{c.id} is already in main at {main.id}, which supersedes it; "
                                  "approve a newer commit")
            if main is None or self.is_ancestor(domain, main.id, c.id):
                target = c                                         # fast-forward
                self._move(dirp, MAIN, c.id)
            else:
                m = self.merge3(domain, main.id, c.id)
                if m.conflicts:
                    raise MergeConflict(m.conflicts)
                raw = m.merged["domain"]
                try:
                    errors = [i for i in validate_domain(Domain.model_validate({"version": 1, **raw}))
                              if i.severity == "error"]
                except ValidationError as e:
                    raise CommitError(f"the merge of {c.id} into main does not parse: {e}") from None
                if errors:
                    raise CommitError(f"the merge of {c.id} into main does not validate: "
                                      + "; ".join(f"{i.code} at {i.where}" for i in errors[:3]))
                target = self._write(dirp, domain, raw, m.merged["representations"], [main.id, c.id],
                                     f"merge {c.id} into main", MAIN)
            self._append(dirp / "approvals.jsonl", {"commit": target.id, "approver": approver, "at": _now(),
                                                    **({"merged": c.id} if target.id != c.id else {})})
            return target

    # -- the semantic diff ------------------------------------------------------------------------
    def diff(self, domain: str, a: str | None, b: str) -> dict[str, Any]:
        """Elements of `b` that changed directly since `a` (None: since nothing). The owner
        re-confirms `to_review`; indirect effects are the change check's to report."""
        new = review_elements(self.domain(domain, b))
        old = review_elements(self.domain(domain, a)) if a else {}
        r = review_diff(old, new)
        return {"changed": r.changed, "added": r.added, "removed": r.removed, "to_review": r.to_review}


__all__ = ["DEFAULT_BRANCH", "MAIN", "Commit", "CommitError", "CommitStore", "Conflict", "Merge", "MergeConflict",
           "content_id"]
