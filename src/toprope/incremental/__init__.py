"""Incremental checking (ADR-0013; M0a sub-PR 9): the dependency graph, the impact report,
affected-only test runs and a result cache.

- **Tests.** The harness's tests at the model level: one per case (`cell:…`, `precondition:…`,
  `create:…`), one per scenario (`flow:<id>`), and the gate-tier exploration (`explore`).
- **Dependencies** come statically from the declaration. A case depends on everything about
  its action (the action, its params, preconditions and matrix cells), on every object
  reachable from the action's object through links (their properties, links, invariants and
  stage fields), on roles, handoffs and fixtures, and on the case itself as the planner built
  it (instance, params, expectation). A cell test reads only its own matrix cell; the rest of
  the matrix reaches it through the instance the small world grew, which is in the key. Flows and exploration depend on the whole declaration's
  shape (text excluded). When unsure, a test depends on more, never less.
- **Cache keys** are hashes of a test's inputs plus the toolchain hash, so a result is reused
  only while nothing it depends on, and no kernel code, has changed.
- **Impact report**, before anything runs: the changed elements and the tests they affect,
  in domain terms ("changes 1 cell; affects 6 cell tests, 3 flows and exploration").
- **Soundness.** `selection_misses` runs everything uncached and lists tests that fail there
  but passed from the cache: bugs in this analysis (target 0).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..decl import (
    Domain,
    diff_interface,
    interface,
    review_contents,
    review_diff,
    review_elements,
)
from ..decl.interface import _strip_text

Key = str


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@functools.lru_cache(maxsize=1)
def toolchain() -> str:
    from ..deploy import toolchain_hash
    return toolchain_hash()


# -- the dependency graph ---------------------------------------------------------------------------
def reach(d: Domain, obj: str) -> set[str]:
    """Object types reachable from `obj` through links, either direction (conservative)."""
    seen, todo = set(), [obj]
    while todo:
        o = todo.pop()
        if o in seen or o not in d.objects:
            continue
        seen.add(o)
        for link in d.links.values():
            if link.from_ == o:
                todo.append(link.to)
            if link.to == o:
                todo.append(link.from_)
    return seen


def action_deps(d: Domain, action: str, keys: set[str]) -> set[str]:
    """The element keys a test of `action` reads."""
    a = d.actions[action]
    objs = reach(d, a.object_type)
    out = set()
    for k in keys:
        kind, _, rest = k.partition(":")
        if kind == "action" and rest == action:
            out.add(k)
        elif kind in ("param", "precondition") and rest.split(".", 1)[0] == action:
            out.add(k)
        elif kind == "cell" and rest.rsplit(".", 1)[-1] == action:
            out.add(k)
        elif kind in ("object", "stages") and rest in objs:
            out.add(k)
        elif kind == "property" and rest.split(".", 1)[0] in objs:
            out.add(k)
        elif kind == "link":
            link = d.links.get(rest)
            if link is None or link.from_ in objs or link.to in objs:
                out.add(k)
        elif kind in ("role", "handoff", "fixture"):
            out.add(k)
        elif kind == "invariant":
            inv = next((i for i in d.invariants if i.id == rest), None)
            if inv is None or inv.on in objs:
                out.add(k)
    return out


def shape(d: Domain) -> str:
    """The whole declaration without its text (descriptions, reasons, glossary terms, purpose):
    what flows and exploration depend on."""
    return _h({k: _strip_text(v) for k, v in review_contents(d).items() if not k.startswith(("term:", "purpose"))})


@dataclass
class Test:
    id: str
    kind: str                         # case | flow | explore
    action: str | None
    deps: set[str] = field(default_factory=set)
    key: str = ""


def tests_of(d: Domain, planner_cases: list[Any] | None = None, examples: int = 50) -> list[Test]:
    """Every model-level test of a declaration, with its dependencies and cache key."""
    contents = review_contents(d)
    keys = set(contents)
    tc = toolchain()
    body = {k: _h(v) for k, v in contents.items()}
    if planner_cases is None:
        from ..harness.cases import Planner
        from ..harness.run import NOW
        from ..harness.world import grow_world
        planner_cases = Planner(grow_world(d, lambda: NOW), lambda: NOW).cases()
    out = []
    per_action: dict[str, set[str]] = {}
    for c in planner_cases:
        deps = per_action.setdefault(c.action, action_deps(d, c.action, keys))
        if c.kind == "cell":       # a cell test reads its own cell; the others reach it through `instance`
            own = f"cell:{c.obj}.{c.state}.{c.action}"
            deps = {k for k in deps if not k.startswith("cell:") or k == own}
        case = {"kind": c.kind, "obj": c.obj, "state": c.state, "action": c.action, "role": c.role,
                "params": c.params, "expect": c.expect, "gap": c.gap,
                "instance": c.instance.data if c.instance is not None else None}
        key = _h({"tc": tc, "test": c.id, "case": case, "deps": {k: body[k] for k in sorted(deps)}})
        out.append(Test(c.id, "case", c.action, deps, key))
    whole = shape(d)
    for sc in d.scenarios:
        out.append(Test(f"flow:{sc.id}", "flow", None, keys, _h({"tc": tc, "flow": sc.id, "shape": whole})))
    out.append(Test("explore", "explore", None, keys, _h({"tc": tc, "explore": examples, "shape": whole})))
    return out


# -- the impact report ------------------------------------------------------------------------------
def impact(new: Domain, old: Domain | None, examples: int = 50) -> dict[str, Any]:
    """Before anything runs: the changed elements and the tests and past actions they affect."""
    t0 = time.perf_counter()
    r = review_diff(review_elements(old) if old else {}, review_elements(new))
    changed = set(r.changed) | set(r.added) | set(r.removed)
    text_only = set(diff_interface(interface(old), interface(new)).text_only) & set(r.changed) if old else set()
    tests = tests_of(new, examples=examples)
    shape_changed = bool(changed - text_only) or old is None
    affected = [t for t in tests
                if (t.kind == "case" and t.deps & changed) or (t.kind != "case" and shape_changed)]
    actions = sorted({t.action for t in affected if t.action} | {k.split(":", 1)[1] for k in changed
                                                                 if k.startswith("action:")})
    kinds: dict[str, int] = {}
    for k in changed:
        kinds[k.split(":", 1)[0]] = kinds.get(k.split(":", 1)[0], 0) + 1
    by_kind = {"cell": 0, "precondition": 0, "create": 0}
    for t in affected:
        if t.kind == "case":
            by_kind[t.id.split(":", 1)[0]] = by_kind.get(t.id.split(":", 1)[0], 0) + 1
    flows = [t.id for t in affected if t.kind == "flow"]
    parts = [f"{n} {kind} test(s)" for kind, n in by_kind.items() if n]
    if flows:
        parts.append(f"{len(flows)} flow(s)")
    if any(t.kind == "explore" for t in affected):
        parts.append("exploration")
    what = ", ".join(f"{n} {k}(s)" for k, n in sorted(kinds.items())) or "nothing"
    summary = f"changes {what}; affects {', '.join(parts) or 'no tests'}"
    if actions:
        summary += f"; replays past {', '.join(actions)}"
    return {"changed": sorted(changed), "text_only": sorted(text_only), "tests": len(tests),
            "affected": [t.id for t in affected], "actions": actions, "summary": summary,
            "seconds": round(time.perf_counter() - t0, 3)}


# -- the result cache -------------------------------------------------------------------------------
class ResultCache:
    """Test results keyed by input hash, one file per key (atomic writes). Results are a list
    of findings (empty: passed)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: Key) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: Key) -> list[dict[str, Any]] | None:
        p = self._path(key)
        try:
            return json.loads(p.read_text())["findings"] if p.exists() else None
        except (json.JSONDecodeError, KeyError, OSError):
            return None                                   # a damaged entry is a miss, never a pass

    def put(self, key: Key, test: str, findings: list[dict[str, Any]]) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-")
        with os.fdopen(fd, "w") as f:
            json.dump({"test": test, "findings": findings}, f, default=str)
        os.replace(tmp, p)


# -- affected-only runs -----------------------------------------------------------------------------
@dataclass
class Run:
    findings: list[Any]               # harness Findings (cached ones rebuilt)
    world: Any                        # the small world (unreachable states)
    undecided: list[str]              # every undecided cell, missing ones included
    stats: dict[str, Any]
    results: dict[str, list[dict[str, Any]]]   # test id → findings (for soundness)


def run_tests(d: Domain, *, examples: int = 50, cache: ResultCache | None = None) -> Run:
    """Run the model-level harness, reusing cached results for unchanged tests."""
    from ..harness.cases import raw_cell
    from ..harness.explore import explore
    from ..harness.run import Finding, Harness
    t0 = time.perf_counter()
    h = Harness(d, levels=("model",))
    cases = h.planner.cases()
    tests = {t.id: t for t in tests_of(d, cases, examples)}
    results: dict[str, list[dict[str, Any]]] = {}
    cached = 0

    def hit(tid: str) -> bool:
        nonlocal cached
        got = cache.get(tests[tid].key) if cache is not None else None
        if got is None:
            return False
        results[tid] = got
        cached += 1
        return True

    todo = [c for c in cases if not hit(c.id)]
    if todo:
        before = len(h.findings)
        h.run_cases("model", todo)
        new = h.findings[before:]
        for c in todo:
            results[c.id] = [asdict(f) for f in new if f.case == c.id]
    for sc in d.scenarios:
        tid = f"flow:{sc.id}"
        if not hit(tid):
            sub = Harness(d.model_copy(update={"scenarios": [sc]}), levels=("model",))
            sub.world, sub.planner = h.world, h.planner
            sub.flows("model")
            results[tid] = [asdict(f) for f in sub.findings]
    if examples and not hit("explore"):
        minimal = explore(h, examples=examples)
        results["explore"] = [asdict(Finding("exploration", "model", "explore", minimal))] if minimal else []
    if cache is not None:
        for tid, fs in results.items():
            cache.put(tests[tid].key, tid, fs)
    findings = [Finding(**f) for tid in results for f in results[tid]]
    undecided = sorted({f"{obj}.{st}.{a}" for obj, tr in d.transitions.items() for st in tr.matrix
                        for a, act in d.actions.items() if act.target == obj and act.creates is None
                        for role in h.world.actors if raw_cell(d, obj, st, a, role) == "undecided"})
    stats = {"tests": len(results), "run": len(results) - cached, "cached": cached,
             "seconds": round(time.perf_counter() - t0, 3)}
    return Run(findings, h.world, undecided, stats, results)


def selection_misses(d: Domain, *, examples: int = 50, cache: ResultCache) -> list[str]:
    """The background soundness check: tests that fail on an uncached run but pass from the
    cache. Each one is a bug in impact analysis."""
    fresh = run_tests(d, examples=examples, cache=None).results
    tests = tests_of(d, examples=examples)
    out = []
    for t in tests:
        was = cache.get(t.key)
        if was is not None and not was and fresh.get(t.id):
            out.append(t.id)
    return sorted(out)


__all__ = ["ResultCache", "Run", "Test", "action_deps", "impact", "reach", "run_tests", "selection_misses",
           "shape", "tests_of", "toolchain"]
