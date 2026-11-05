"""The commit store (ADR-0029): Authoring as an immutable commit log, Delivery as a ref.

Layout under `<root>/<domain>/`:
  objects/<content>/domain.yaml       the declaration without `version`, stored once per content
  objects/<content>/representations/  its representations, if any (a released UI is the pair)
  log.jsonl                           one line per commit: id, seq, content, parents, at, interface
  refs.jsonl                          one line per ref move: branch, commit, at (ADR-0033)
  approvals.jsonl                     one line per approval: commit, approver, at (never removed)
  checks.jsonl                        one line per check run on a commit (ADR-0032): commit, check,
                                      ok, summary, base, at (append-only, like approvals)

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
    review_contents,
    review_diff,
    review_elements,
    validate_domain,
)
from ..decl.interface import review_hash

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
    author: str = ""             # who compiled it (ADR-0032); "" when not known


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


def _element_conflicts(base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any],
                       merged: dict[str, Any]) -> list[Conflict]:
    """ADR-0033: an element (by review hash) changed differently on both sides is a conflict,
    even when the two sides changed different fields of it. Added on both sides with
    different content counts too. An element both sides changed from a base is not listed
    when the merge kept ours whole: then every change theirs made is a path conflict already."""
    def contents(raw: dict[str, Any]) -> dict[str, Any]:
        try:
            return review_contents(Domain.model_validate({"version": 1, **raw})) if raw else {}
        except ValidationError as e:
            raise CommitError(f"a commit in this merge does not parse: {e}") from None
    b, o, t = contents(base), contents(ours), contents(theirs)
    try:
        m = review_contents(Domain.model_validate({"version": 1, **merged}))
    except ValidationError:
        m = {}                                       # the merge check reports it; list every element
    h = lambda x, k: review_hash(x[k]) if k in x else None  # noqa: E731
    out = []
    for k in sorted(set(o) | set(t)):
        if k.startswith("fixture:") and k.endswith(".None"):
            continue                                 # fixtures without an id are not one element
        if h(o, k) != h(b, k) and h(t, k) != h(b, k) and h(o, k) != h(t, k) \
                and not (k in b and h(m, k) == h(o, k)):
            out.append(Conflict(f"element:{k}", b.get(k), o.get(k), t.get(k)))
    return out


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
        path = self._dir(domain) / "refs.jsonl"
        if not path.exists():
            return self._legacy_refs(domain)
        out: dict[str, str] = {}
        for r in self._lines(path):
            out[r["branch"]] = r["commit"]
        return out

    def _legacy_refs(self, domain: str) -> dict[str, str]:
        """A store written before branches (ADR-0029: one line of commits) has no refs file. Its
        refs are derived: `work` is the last commit, `main` the newest approved one."""
        log = self.log(domain)
        if not log:
            return {}
        approved = {a["commit"] for a in self.approvals(domain)}
        out = {DEFAULT_BRANCH: log[-1].id}
        main = max((c for c in log if c.id in approved), key=lambda c: c.seq, default=None)
        if main is not None:
            out[MAIN] = main.id
        return out

    def head(self, domain: str, branch: str = DEFAULT_BRANCH) -> Commit | None:
        cid = self.refs(domain).get(branch)
        return self.get(domain, cid) if cid else None

    def main(self, domain: str) -> Commit | None:
        return self.head(domain, MAIN)

    @staticmethod
    def _reach(parents: dict[str, list[str]], commit_id: str) -> set[str]:
        seen, todo = set(), [commit_id]
        while todo:
            c = todo.pop()
            if c not in seen and c in parents:
                seen.add(c)
                todo.extend(parents[c])
        return seen

    def ancestors(self, domain: str, commit_id: str) -> set[str]:
        """The commit and everything it descends from."""
        return self._reach({c.id: c.parents for c in self.log(domain)}, commit_id)

    def is_ancestor(self, domain: str, a: str, b: str) -> bool:
        """True if `a` is `b` or an ancestor of `b`."""
        return a in self.ancestors(domain, b)

    def merge_base(self, domain: str, a: str, b: str) -> str | None:
        """The nearest common ancestor: a common ancestor no other common ancestor descends from.
        The log is read once."""
        log = self.log(domain)
        parents = {c.id: c.parents for c in log}
        common = self._reach(parents, a) & self._reach(parents, b)
        covered: set[str] = set()                          # strict ancestors of a common ancestor
        for c in common:
            for p in parents[c]:
                if p not in covered:
                    covered |= self._reach(parents, p)
        seq = {c.id: c.seq for c in log}
        return max(common - covered, key=seq.__getitem__, default=None)

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
        bodies = [self._body(domain, x) for x in (base, ours, theirs)]
        conflicts: list[Conflict] = []
        merged = _merge3(*bodies, "", conflicts)
        conflicts += _element_conflicts(*(b["domain"] for b in bodies), merged["domain"])
        return Merge(base, merged, conflicts)

    # -- writing ----------------------------------------------------------------------------------
    def commit(self, declaration: str | Path, representations: list[str | Path] | None = None,
               message: str = "", branch: str = DEFAULT_BRANCH, merge: str | None = None,
               author: str = "") -> tuple[Commit, bool]:
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
        cid = content_id(raw, reps)
        with self._lock(d.domain) as dirp:
            log = self.log(d.domain)
            # A new branch starts from `main`; before the first approval, from the domain's first
            # commit, so every branch shares a base (ADR-0033: main exists from the first commit).
            head = self.head(d.domain, branch) or self.main(d.domain) or (log[0] if log else None)
            if merge is not None:
                self.get(d.domain, merge)
                if head is not None and self.is_ancestor(d.domain, merge, head.id):
                    merge = None                       # already merged: an ordinary commit
            if head is not None and merge is None and head.content == cid:
                if self.refs(d.domain).get(branch) != head.id:
                    self._move(dirp, branch, head.id)
                return head, False
            parents = ([head.id] if head else []) + ([merge] if merge else [])
            return self._write(dirp, d, raw, reps, cid, parents, message, branch, author), True

    def _write(self, dirp: Path, d: Domain, raw: dict[str, Any], reps: dict[str, Any], cid: str,
               parents: list[str], message: str, branch: str, author: str = "") -> Commit:
        """Store a commit and move `branch` to it. Called under the domain lock."""
        domain = d.domain
        seq = max((c.seq for c in self.log(domain)), default=0) + 1
        iface = "1.0.0"
        if parents:
            first = self.get(domain, parents[0])
            iface = _bump(first.interface, diff_interface(interface(self.domain(domain, first.id)), interface(d)).bump)
        c = Commit(f"{seq}-{cid}", seq, domain, cid, parents, _now(), iface, message, branch, author)
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
        self._keep_legacy_refs(dirp)
        self._append(dirp / "log.jsonl", asdict(c))
        self._move(dirp, branch, c.id)
        return c

    def _keep_legacy_refs(self, dirp: Path) -> None:
        """A store from before branches: write its derived refs before anything else changes."""
        refs = dirp / "refs.jsonl"
        if not refs.exists():                        # written whole, then renamed: never half there
            lines = [json.dumps({"branch": b, "commit": c, "at": _now(), "derived": True}, sort_keys=True) + "\n"
                     for b, c in self._legacy_refs(dirp.name).items()]
            fd, tmp = tempfile.mkstemp(dir=dirp, prefix=".refs-")
            with os.fdopen(fd, "w") as f:
                f.writelines(lines)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, refs)

    def _move(self, dirp: Path, branch: str, commit_id: str) -> None:
        self._keep_legacy_refs(dirp)
        self._append(dirp / "refs.jsonl", {"branch": branch, "commit": commit_id, "at": _now()})

    @staticmethod
    def representations_for(domain: str, folder: Path, strict: bool = True) -> list[Path]:
        """The `*.representation.yaml` files next to a declaration that target its domain. A file
        that cannot be read is an error, never skipped: a release would silently lose its UI.
        (`strict=False` skips it, for a forced checkout that overwrites the working copy.)"""
        out = []
        for p in sorted(folder.glob("*.representation.yaml")):
            try:
                body = load_yaml(p.read_text()) or {}
            except Exception as e:
                if not strict:
                    continue
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
            if self.is_approved(domain, c.id) or any(a.get("merged") == c.id for a in self.approvals(domain)):
                return None                                  # approved already, directly or by a merge
            main = self.main(domain)
            if main is not None and self.is_ancestor(domain, c.id, main.id):
                raise CommitError(f"{c.id} is already in main at {main.id}, which supersedes it; "
                                  "approve a newer commit")
            if main is None or self.is_ancestor(domain, main.id, c.id):
                body = self._body(domain, c.id)               # fast-forward: main takes this commit
                self._check(c.id, body["domain"])               # (a resolved merge comes this way too)
                target = c
                self._move(dirp, MAIN, c.id)
            else:
                m = self.merge3(domain, main.id, c.id)
                if m.conflicts:
                    raise MergeConflict(m.conflicts)
                d = self._check(c.id, m.merged["domain"])
                reps = m.merged["representations"]
                target = self._write(dirp, d, m.merged["domain"], reps, content_id(m.merged["domain"], reps),
                                     [main.id, c.id], f"merge {c.id} into main", MAIN, approver)
            self._append(dirp / "approvals.jsonl", {"commit": target.id, "approver": approver, "at": _now(),
                                                    **({"merged": c.id} if target.id != c.id else {})})
            return target

    @staticmethod
    def _check(commit_id: str, raw: dict[str, Any]) -> Domain:
        """What `main` takes must validate: each side may be valid alone and not together."""
        try:
            d = Domain.model_validate({"version": 1, **raw})
        except ValidationError as e:
            raise CommitError(f"main with {commit_id} does not parse: {e}") from None
        errors = [i for i in validate_domain(d) if i.severity == "error"]
        if errors:
            raise CommitError(f"main with {commit_id} does not validate: "
                              + "; ".join(f"{i.code} at {i.where}" for i in errors[:3]))
        return d

    # -- check records (ADR-0032) -----------------------------------------------------------
    def record_check(self, domain: str, commit_id: str, check: str, ok: bool | None, summary: str,
                     base: str | None = None) -> dict[str, Any]:
        """Append the result of one check run on a commit (see `record_checks`)."""
        return self.record_checks(domain, commit_id, [(check, ok, summary)], base)[0]

    def record_checks(self, domain: str, commit_id: str, rows: list[tuple[str, bool | None, str]],
                      base: str | None = None) -> list[dict[str, Any]]:
        """Append the results of one run of checks on a commit, in one write under the lock, with
        one run id. `ok` None means the check did not run in this run. Never rewritten: a later
        run appends newer records, and the newest record of each check is its status."""
        with self._lock(domain) as dirp:
            self.get(domain, commit_id)
            at = _now()
            run = hashlib.sha256(f"{commit_id}|{at}|{os.getpid()}|{id(rows)}".encode()).hexdigest()[:12]
            entries = [{"commit": commit_id, "check": name, "ok": ok if ok is None else bool(ok),
                        "summary": summary, "base": base, "at": at, "run": run} for name, ok, summary in rows]
            with open(dirp / "checks.jsonl", "a") as f:
                f.write("".join(json.dumps(e, sort_keys=True) + "\n" for e in entries))
                f.flush()
                os.fsync(f.fileno())
            return entries

    def checks(self, domain: str, commit_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._lines(self._dir(domain) / "checks.jsonl")
        return [r for r in rows if commit_id is None or r["commit"] == commit_id]

    def check_status(self, domain: str, commit_id: str) -> dict[str, dict[str, Any]]:
        """The newest record of each check on a commit (`ok` None: it did not run that time)."""
        out: dict[str, dict[str, Any]] = {}
        for r in self.checks(domain, commit_id):
            out[r["check"]] = r
        return out

    # -- history and checkout (ADR-0032) --------------------------------------------------------
    def element_log(self, domain: str, key: str, at: str | None = None) -> list[dict[str, Any]]:
        """An element's history, like `git log -- path`: every commit reachable from `at` (default:
        what `main` points to, else the `work` head) that added, changed or removed the element,
        or changed its provenance (`source`, `status`: what it cites, and whether it is
        confirmed). Oldest first. A merge commit is listed only when the element differs from
        every parent, so a change that came in from a parent is credited where it was made."""
        log = self.log(domain)
        by_id = {c.id: c for c in log}
        if at is None:
            head = self.main(domain) or self.head(domain)
            if head is None:
                return []
            at = head.id
        elif at not in by_id:
            raise CommitError(f"no commit {at} in {domain}")
        reach = self._reach({c.id: c.parents for c in log}, at)
        cache: dict[str, dict[str, Any]] = {}

        def element(commit_id: str | None) -> Any:
            if commit_id is None:
                return None
            c = by_id[commit_id]
            if c.content not in cache:                 # read the object directly: no log re-reads
                raw = load_yaml((self._dir(domain) / "objects" / c.content / "domain.yaml").read_text()) or {}
                cache[c.content] = review_contents(Domain.model_validate({**raw, "version": c.seq}))
            return cache[c.content].get(key)

        def provenance(e: Any) -> dict[str, Any]:
            return {k: e.get(k) for k in ("source", "status")} if isinstance(e, dict) else {}
        def same(x: Any, y: Any) -> bool:
            return (x is None and y is None) or (x is not None and y is not None and review_hash(x) == review_hash(y)
                                                 and provenance(x) == provenance(y))
        out = []
        for c in (c for c in log if c.id in reach):
            new = element(c.id)
            parents = [element(p) for p in c.parents] or [None]
            if any(same(new, old) for old in parents):
                continue                              # unchanged from a parent: it came from there
            old = parents[0]
            if old is None:
                change = "added"
            elif new is None:
                change = "removed"
            elif review_hash(new) != review_hash(old):
                change = "changed"
            elif provenance(new) != provenance(old):
                change = "provenance"
            else:
                continue
            out.append({"commit": c.id, "seq": c.seq, "at": c.at, "author": c.author, "message": c.message,
                        "change": change, **provenance(new if new is not None else old)})
        return out

    def working_copy(self, domain: str, declaration: str | Path, strict: bool = True) -> tuple[str | None, list[Path]]:
        """The working copy's content id (None when it has no declaration) and this domain's
        representation files next to it. Unreadable files are a CommitError when `strict`;
        otherwise they are left out, so a forced overwrite can still recover."""
        path = Path(declaration)
        folder = path.parent
        present = self.representations_for(domain, folder, strict=strict) if folder.exists() else []
        if not strict:
            return None, present
        try:
            reps = {p.name: load_yaml(p.read_text()) for p in present}
            raw = (load_yaml(path.read_text()) or {}) if path.exists() else None
        except Exception as e:                       # noqa: BLE001 - any parse error: report the file
            raise CommitError(f"cannot read the working copy: {e}") from None
        return (content_id(raw, reps) if raw is not None else None), present

    def write_working_copy(self, domain: str, body: dict[str, Any], declaration: str | Path, version: int,
                           present: list[Path]) -> None:
        """Write a body (declaration and representations) into a working copy, under the domain
        lock: every file goes to a temporary name first, then all are renamed in place, then
        this domain's representations the body lacks are removed."""
        path = Path(declaration)
        folder = path.parent
        folder.mkdir(parents=True, exist_ok=True)
        decl = body["domain"]
        out = {"domain": decl.get("domain"), "version": version, **{k: v for k, v in decl.items() if k != "domain"}}
        files = {path: yaml.safe_dump(out, sort_keys=False, allow_unicode=True)}
        files.update({folder / name: yaml.safe_dump(r, sort_keys=False, allow_unicode=True)
                      for name, r in body["representations"].items()})
        with self._lock(domain):
            staged = []
            try:
                for target, text in files.items():
                    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{target.name}.")  # same folder: rename is atomic
                    with os.fdopen(fd, "w") as f:
                        f.write(text)
                    staged.append((tmp, target))
            except BaseException:
                for tmp, _ in staged:
                    os.unlink(tmp)
                raise
            for tmp, target in staged:
                os.replace(tmp, target)
            for p in present:
                if p.name not in body["representations"] and p.exists():
                    p.unlink()

    def checkout(self, domain: str, commit_id: str, declaration: str | Path, force: bool = False) -> Commit:
        """Load a commit's content into a working copy: its declaration and its representations,
        removing this domain's representations it does not have. The draft keeps its `version`
        (a new working copy takes the commit's sequence number). Committing the result makes a
        new commit, so a revert is a commit. Refused when the working copy holds content no
        commit has (uncommitted changes, including a UI next to a missing declaration), unless
        `force`; a forced checkout also recovers from an unreadable working copy."""
        c = self.get(domain, commit_id)
        path = Path(declaration)
        if force:
            _, present = self.working_copy(domain, path, strict=False)
        else:
            current, present = self.working_copy(domain, path)
            known = {x.content for x in self.log(domain)}
            if (current is not None and current not in known) or (current is None and present):
                raise CommitError(f"{path.name} has changes no commit holds: commit them first")
        version = c.seq
        try:
            draft = load_yaml(path.read_text()) if path.exists() else None
            if isinstance(draft, dict) and isinstance(draft.get("version"), int):
                version = draft["version"]
        except Exception:  # noqa: BLE001, S110 - only under force: the draft is overwritten
            pass
        self.write_working_copy(domain, self._body(domain, c.id), path, version, present)
        return c

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
