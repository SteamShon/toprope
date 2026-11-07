"""The change check (ADR-0009, ADR-0018; M0a sub-PR 8): compare a new declaration with the
current one, and report what would break or conflict before anything is deployed.

Checks, in order (each reports problems as `error`, `warning` or `info`; the change passes
when no check reports an error):
- **structural**: the declaration's references and types (`validate_domain`). Errors fail.
- **semantic**: rules that cannot all hold: states the small world can no longer reach,
  actions no matrix cell allows any more, and cells still `undecided` (listed, ADR-0010).
  Newly unreachable states and newly dead actions are errors; existing ones are warnings.
- **scenarios** (scenario regression): every scenario of the current version, and the new
  one's, run against the new model. A scenario that fails is an error.
- **harness**: the generated harness on the new declaration (cells, invariants, gate-tier
  exploration, flows). Any finding is an error.
- **log_replay**: past actions from an event store, re-decided by the new model in their
  original order and clock: "with this change, 12 past actions would have been blocked".
  Blocked actions are errors; actions that would now change different fields are warnings.
- **in_flight**: objects in that store whose type or state the new declaration lacks
  (stranded; migration plans come in M0b). Errors.
- **nl**: natural-language conflicts in descriptions and judgment rules, by an `NLChecker`
  (an LLM in practice). Warnings only; skipped when no checker is configured.

Indirect effects are reported here; only directly changed elements are re-reviewed
(ADR-0029). The incremental version (impact report, affected-only reruns) is sub-PR 9.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from ..decl import (
    Domain,
    diff_interface,
    interface,
    review_diff,
    review_elements,
    validate_domain,
)
from ..semantics.interpreter import Interpreter
from ..semantics.model import project
from ..semantics.types import Actor, Command, Event, Grant
from ..store import EventStore, MemoryEventStore

EPOCH = datetime.min.replace(tzinfo=timezone.utc)   # for events without a time
CHECKS = ("structural", "semantic", "scenarios", "harness", "log_replay", "in_flight", "nl")


@dataclass(frozen=True)
class Problem:
    severity: str            # error | warning | info
    where: str               # an element key, a scenario step, or a stream
    message: str


@dataclass
class CheckResult:
    name: str
    ran: bool = True
    problems: list[Problem] = field(default_factory=list)
    note: str = ""           # why it did not run, or what it covered

    @property
    def ok(self) -> bool:
        return not any(p.severity == "error" for p in self.problems)

    def add(self, severity: str, where: str, message: str) -> None:
        self.problems.append(Problem(severity, where, message))

    def summary(self) -> str:
        if not self.ran:
            return f"skipped: {self.note}"
        errs = sum(p.severity == "error" for p in self.problems)
        warns = sum(p.severity == "warning" for p in self.problems)
        return f"{errs} error(s), {warns} warning(s)" + (f"; {self.note}" if self.note else "")


@dataclass
class ChangeReport:
    domain: str
    diff: dict[str, Any]
    checks: dict[str, CheckResult]
    impact: dict[str, Any] | None = None       # the impact report (ADR-0013), computed first
    timings: dict[str, Any] = field(default_factory=dict)
    selection_misses: list[str] | None = None   # with a full run: tests the cache wrongly passed

    @property
    def sound(self) -> bool:
        return not self.selection_misses

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks.values())

    @property
    def errors(self) -> int:
        return sum(p.severity == "error" for c in self.checks.values() for p in c.problems)

    @property
    def warnings(self) -> int:
        return sum(p.severity == "warning" for c in self.checks.values() for p in c.problems)

    def summary(self) -> str:
        failing = [n for n, c in self.checks.items() if not c.ok]
        head = "passes" if self.ok else f"fails: {', '.join(failing)}"
        return f"{head}; {self.errors} error(s), {self.warnings} warning(s)"

    def to_json(self) -> dict[str, Any]:
        return {"domain": self.domain, "ok": self.ok, "errors": self.errors, "warnings": self.warnings,
                "summary": self.summary(), "diff": self.diff, "impact": self.impact, "timings": self.timings,
                **({"selection_misses": self.selection_misses} if self.selection_misses is not None else {}),
                "checks": {n: {"ok": c.ok, "ran": c.ran, "summary": c.summary(), "note": c.note,
                               "problems": [asdict(p) for p in c.problems]} for n, c in self.checks.items()}}


class NLChecker(Protocol):
    """Finds natural-language conflicts (descriptions, judgment rules). An LLM adapter in
    practice; its findings are warnings, never errors (ADR-0009)."""

    def conflicts(self, old: Domain | None, new: Domain, changed: list[str]) -> list[tuple[str, str]]: ...


# -- the pipeline -------------------------------------------------------------------------------
def change_check(new: Domain, old: Domain | None = None, *, events: EventStore | None = None,
                 nl: NLChecker | None = None, examples: int = 50, cache: Any = None, full: bool = False,
                 roles_of: Callable[[dict[str, Any], str], tuple[str, ...]] | None = None) -> ChangeReport:
    """Run every check of `new` against `old` (None: the first version). `events` is the
    deployed environment's event store, for log replay and the in-flight check. `roles_of`
    resolves a past actor's roles (the Identity port); without it, an actor is assumed to have
    had every role the current version allowed for that action. `cache` (a ResultCache)
    reuses the results of tests whose inputs did not change (ADR-0013); `full` then also runs
    every test uncached and lists the selection misses (tests the cache wrongly passed)."""
    from ..incremental import impact as impact_of
    checks: dict[str, CheckResult] = {}
    timings: dict[str, float] = {}
    old_issues = validate_domain(old) if old else []
    checks["structural"] = _structural(new, old, old_issues)
    structurally_ok = checks["structural"].ok
    # A base with errors is no baseline: nothing is reported as newly lost against it.
    baseline = old if old is not None and not any(i.severity == "error" for i in old_issues) else None
    misses = impact = None
    if full and cache is None:
        raise ValueError("a full run compares with the result cache: it needs one")
    if structurally_ok:
        from ..harness.run import Harness
        ids = {sc.id for sc in new.scenarios}
        carried = [sc for sc in (old.scenarios if old else []) if sc.id not in ids]
        tested = new.model_copy(update={"scenarios": list(new.scenarios) + carried})
        h = Harness(tested, levels=("model",))                 # one small world for the whole check
        cases = h.planner.cases()
        impact = impact_of(new, baseline, examples, cases)
        checks["semantic"], checks["scenarios"], checks["harness"], stats = \
            _model_checks(tested, carried, baseline, examples, cache, h)
        timings["harness"] = stats["seconds"]
        if full:
            from ..incremental import selection_misses
            misses = selection_misses(tested, examples=examples, cache=cache, cases=cases)
    else:
        for name in ("semantic", "scenarios", "harness"):
            checks[name] = CheckResult(name, ran=False, note="the declaration has structural errors")
    if events is None:
        for name in ("log_replay", "in_flight"):
            checks[name] = CheckResult(name, ran=False, note="no event store (nothing deployed)")
    else:
        checks["in_flight"] = in_flight(new, events)
        checks["log_replay"] = log_replay(new, old, events, roles_of,
                                          only=set(impact["actions"]) if impact and old is not None else None) \
            if structurally_ok else CheckResult("log_replay", ran=False, note="the declaration has structural errors")
    diff = _diff(new, old)
    checks["nl"] = _nl(new, old, nl, diff["to_review"])
    report = ChangeReport(new.domain, diff, {n: checks[n] for n in CHECKS})
    report.impact = impact
    report.timings = {**timings, "impact": impact["seconds"] if impact else None}
    report.selection_misses = misses
    return report


def check_commit(commits: Any, domain: str, commit_id: str, base: str | None = "merge-base", *,
                 events: EventStore | None = None, nl: NLChecker | None = None, examples: int = 50,
                 cache: Any = None, full: bool = False,
                 roles_of: Callable[[dict[str, Any], str], tuple[str, ...]] | None = None) -> ChangeReport:
    """Run the change check on a commit of a commit store, and record the result on the commit
    (ADR-0032): one record per check, `ok: null` for one that did not run, plus `change-check`
    for the whole, appended together with one run id. The base is
    the commit's merge base with `main` by default (ADR-0033: a branch is reviewed from there),
    or its first parent when the commit is already in `main` or nothing is approved yet; a
    commit without parents is checked as a first version."""
    c = commits.get(domain, commit_id)
    if base == "merge-base":
        base = commits.review_base(domain, c.id)
    old = commits.domain(domain, base) if base else None
    report = change_check(commits.domain(domain, c.id), old, events=events, nl=nl, examples=examples,
                          cache=cache, full=full, roles_of=roles_of)
    report.diff["from"], report.diff["to"] = base, c.id
    rows = [(name, res.ok if res.ran else None, res.summary()) for name, res in report.checks.items()]
    rows.append(("change-check", report.ok, report.summary()))
    from ..decl.provenance import proposed_elements
    left = proposed_elements(commits.declaration(domain, c.id))
    rows.append(("confirmed", not left, f"{len(left)} proposed element(s)"
                 + (": " + ", ".join(left[:5]) if left else "")))   # approval needs none (ADR-0041)
    commits.record_checks(domain, c.id, rows, base)        # one run, one append: skipped checks too
    return report


def _diff(new: Domain, old: Domain | None) -> dict[str, Any]:
    r = review_diff(review_elements(old) if old else {}, review_elements(new))
    bump = diff_interface(interface(old), interface(new)).bump if old else "initial"
    return {"changed": r.changed, "added": r.added, "removed": r.removed, "to_review": r.to_review,
            "interface_bump": bump}


def _structural(new: Domain, old: Domain | None, old_issues: list[Any]) -> CheckResult:
    res = CheckResult("structural")
    before = {(i.code, i.where) for i in old_issues}
    for i in validate_domain(new):
        sev = i.severity if i.severity == "error" or (i.code, i.where) in before else "warning"
        res.add(sev, i.where, f"{i.code}: {i.message}" + ("" if (i.code, i.where) in before or not old else " (new)"))
    return res


def dead_actions(d: Domain) -> list[str]:
    """Actions on an object with a matrix that no cell allows, for any role."""
    out = []
    for name, a in d.actions.items():
        tr = d.transitions.get(a.object_type) if a.object_type else None
        if tr is None or a.creates is not None:
            continue
        cells = [row.get(name) for row in tr.matrix.values()]
        if not any(_allows(c) for c in cells):
            out.append(name)
    return sorted(out)


def _allows(cell: Any) -> bool:
    from ..decl.models import ByRole, Deny, Target
    if isinstance(cell, Target):
        return True
    if isinstance(cell, Deny) or cell is None:
        return False
    if isinstance(cell, ByRole):
        return any(_allows(v) for v in cell.by_role.values())
    return isinstance(cell, str) and cell not in ("n/a", "undecided")


def _model_checks(tested: Domain, carried: list[Any], baseline: Domain | None, examples: int,
                  cache: Any, h: Any) -> tuple[CheckResult, CheckResult, CheckResult, dict[str, Any]]:
    """One model-level harness pass on the new declaration, with the base's scenarios carried
    along and unchanged tests taken from the cache (ADR-0013): the semantic check (the small
    world's unreachable states, undecided cells), scenario regression (the flows) and the rest
    of the harness findings."""
    from ..harness.world import grow_world
    from ..incremental import run_tests
    new = tested
    run = run_tests(tested, examples=examples, cache=cache, harness=h)

    semantic = CheckResult("semantic")
    unreach_old = grow_world(baseline).unreachable if baseline is not None else {}
    for obj, states in run.world.unreachable.items():
        for st in states:
            newly = baseline is not None and obj in baseline.transitions \
                and st in baseline.transitions[obj].matrix and st not in unreach_old.get(obj, [])
            semantic.add("error" if newly else "warning", f"state:{obj}.{st}",
                         "no longer reachable from the examples" if newly else "not reachable from the examples")
    dead_old = set(dead_actions(baseline)) if baseline is not None else set()
    for a in dead_actions(new):
        newly = baseline is not None and a in baseline.actions and a not in dead_old
        semantic.add("error" if newly else "warning", f"action:{a}",
                     "no matrix cell allows it any more" if newly else "no matrix cell allows it")
    from ..harness.mechanical import unreachable_from_creation
    for obj, states in unreachable_from_creation(tested).items():    # ADR-0035: mechanical, apart
        for st in states:
            semantic.add("warning", f"state:{obj}.{st}", "no declared move reaches it from creation")
    for c in run.undecided:                                # missing cells count as undecided
        semantic.add("info", f"cell:{c}", "undecided")

    scenarios, harness = CheckResult("scenarios"), CheckResult("harness")
    carried_ids = {sc.id for sc in carried}
    failed = set()
    for f in run.findings:
        if f.kind == "flow":
            sid = f.case.split("#")[0]
            failed.add(sid)
            origin = "a scenario the new version removed" if sid in carried_ids else "scenario"
            scenarios.add("error", f"scenario:{f.case}", f"{origin} fails: {f.detail.get('why')}")
        else:
            harness.add("error", f"{f.kind}:{f.case}", _short(f.detail))
    for w in run.warnings:                     # ADR-0035: not inductive / untested, reported, never failing
        harness.add("warning", f"{w.kind}:{w.case}", f"{w.detail.get('reason')}: {w.detail.get('why')}")
    total = len(tested.scenarios)
    scenarios.note = f"{total - len(failed)}/{total} scenarios pass"
    harness.note = (f"{run.stats['tests']} tests: {run.stats['run']} run, {run.stats['cached']} from cache, "
                    f"{run.stats['seconds']} s")
    return semantic, scenarios, harness, run.stats


def _short(detail: dict[str, Any]) -> str:
    text = ", ".join(f"{k}={v}" for k, v in detail.items())
    return text if len(text) <= 300 else text[:297] + "..."


# -- log replay and in-flight (ADR-0018) -----------------------------------------------------------
def _domain_streams(events: EventStore) -> list[tuple[str, list[Event]]]:
    out = []
    for s in events.streams():
        evs = events.read(s)
        if evs and evs[0].kind == "domain":
            out.append((s, evs))
    return out


def in_flight(new: Domain, events: EventStore) -> CheckResult:
    """Objects whose type, or current state, the new declaration lacks (stranded)."""
    res = CheckResult("in_flight")
    n = 0
    for stream, evs in _domain_streams(events):
        n += 1
        obj, st = evs[0].aggregate, project(evs) or {}
        if obj not in new.objects:
            res.add("error", stream, f"{obj} is gone; the object would be stranded")
            continue
        tr = new.transitions.get(obj)
        if tr is not None:
            prop = new.objects[obj].properties.get(tr.field)
            states = set(tr.matrix) | set((prop.enum or []) if prop else []) | {tr.initial}
            if st.get(tr.field) not in states:
                res.add("error", stream, f"its state {st.get(tr.field)!r} is gone; the object would be stranded")
    res.note = f"{n} object(s) checked"
    return res


def log_replay(new: Domain, old: Domain | None, events: EventStore,
               roles_of: Callable[[dict[str, Any], str], tuple[str, ...]] | None = None,
               only: set[str] | None = None) -> CheckResult:
    """Re-decide every past action with the new model, in order, at its original time. The
    replayed store takes the recorded events, not the new ones, so one blocked action does
    not cascade into the rest of history. `only` limits the re-decided actions to the affected
    ones (ADR-0013); the others still advance the replayed state. A past action the base model
    blocks too is not this change's doing: it is counted, not reported, so a change approved
    once does not fail every later check."""
    res = CheckResult("log_replay")
    clock_at: list[datetime] = [EPOCH]
    interp = Interpreter(new, lambda: clock_at[0])
    before = Interpreter(old, lambda: clock_at[0]) if old is not None else None
    replay = MemoryEventStore()

    def lookup(oid: str):
        evs = replay.read(oid)
        return (evs[0].aggregate, project(evs)) if evs else None

    history = [ev for _, evs in _domain_streams(events) for ev in evs if ev.kind == "domain"]
    # By time; ties keep each stream's own order (the sort is stable). Across streams with equal
    # times the true order is unknown: a coarse clock can misorder cross-object lookups.
    history.sort(key=lambda e: e.at or EPOCH)
    replayed = blocked = already = 0
    for ev in history:
        action = (ev.payload or {}).get("action")
        if action is not None and ev.actor is not None and (only is None or action in only):
            replayed += 1
            clock_at[0] = ev.at or clock_at[0]
            cmd = _command(ev, new, old, roles_of)
            found = lookup(ev.stream)
            state = None if found is None else found[1]
            dec = interp.decide(cmd, state, lookup)
            when = ev.at.isoformat() if ev.at else "?"
            if not dec.outcome.ok and before is not None and not before.decide(cmd, state, lookup).outcome.ok:
                already += 1
            elif not dec.outcome.ok:
                blocked += 1
                res.add("error", f"{ev.stream}@{ev.version}",
                        f"{action} by {ev.actor.get('id')} at {when} would now be "
                        f"{dec.outcome.status} ({dec.outcome.code}): {dec.outcome.reason}")
            else:
                was = (ev.payload or {}).get("changes") or {}
                now = next((e.payload.get("changes") for e in dec.events if e.kind == "domain"), {}) or {}
                differ = sorted((set(now) ^ set(was)) | {k for k in set(now) & set(was)
                                                         if now[k] != was[k] and not (_is_time(now[k]) and _is_time(was[k]))})
                if differ:
                    res.add("warning", f"{ev.stream}@{ev.version}", f"{action} at {when} would now set {differ} differently")
        replay.append(ev.stream, replay.version(ev.stream), [_copy(ev)])
    total = sum(1 for ev in history if (ev.payload or {}).get("action") is not None and ev.actor is not None)
    res.note = f"{replayed} of {total} past action(s) re-decided; {blocked} would be blocked" + (
        f"; {already} blocked by the base too" if already else "")
    return res


def _is_time(v: Any) -> bool:
    """A recorded timestamp (now() at the time): replay's clock differs by microseconds."""
    if not isinstance(v, str):
        return False
    try:
        datetime.fromisoformat(v)
        return "T" in v
    except ValueError:
        return False


def _copy(ev: Event) -> Event:
    return Event(ev.type, ev.stream, ev.aggregate, ev.at, copy.deepcopy(ev.actor), copy.deepcopy(ev.payload),
                 ev.kind, None, ev.domain_version, ev.on_behalf_of, ev.grant, ev.thread_id, ev.run_id, ev.causation)


def _command(ev: Event, new: Domain, old: Domain | None,
             roles_of: Callable[[dict[str, Any], str], tuple[str, ...]] | None) -> Command:
    ref = ev.actor or {}
    action = ev.payload["action"]
    kind = ref.get("kind", "person")
    if roles_of is not None:
        roles = tuple(roles_of(ref, action))
    elif kind == "system":            # the kernel replies as `external:kernel`; handoffs as `system`
        rid = str(ref.get("id") or "")
        roles = (rid,) if rid.startswith("external:") else ("system",)
    else:                     # it succeeded then, so the actor held a role the old version allowed
        src = old if old is not None and action in old.actions else new
        a = src.actions.get(action)
        roles = tuple(dict.fromkeys(r if isinstance(r, str) else getattr(r, "role", None)
                                    for r in (a.actor if a else []))) or tuple(src.roles)
        roles = tuple(r for r in roles if r)
    actor = Actor(ref.get("id"), kind, roles)
    principal = grant = None
    if ev.on_behalf_of:
        principal = Actor(ev.on_behalf_of.get("id"), ev.on_behalf_of.get("kind", "person"), roles)
        grant = Grant(ev.grant or "replay", frozenset(new.actions))
    return Command(actor, action, ev.stream, copy.deepcopy(ev.payload.get("params") or {}), at=ev.at,
                   on_behalf_of=principal, grant=grant, thread_id=ev.thread_id, run_id=ev.run_id,
                   causation=ev.causation)


def _nl(new: Domain, old: Domain | None, nl: NLChecker | None, changed: list[str]) -> CheckResult:
    if nl is None:
        return CheckResult("nl", ran=False, note="no natural-language checker configured")
    res = CheckResult("nl")
    for where, message in nl.conflicts(old, new, changed):
        res.add("warning", where, message)                     # never an error (ADR-0009)
    return res


__all__ = [
    "CHECKS",
    "ChangeReport",
    "CheckResult",
    "NLChecker",
    "Problem",
    "change_check",
    "check_commit",
    "dead_actions",
    "in_flight",
    "log_replay",
]
