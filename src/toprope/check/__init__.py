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
                "summary": self.summary(), "diff": self.diff,
                "checks": {n: {"ok": c.ok, "ran": c.ran, "summary": c.summary(), "note": c.note,
                               "problems": [asdict(p) for p in c.problems]} for n, c in self.checks.items()}}


class NLChecker(Protocol):
    """Finds natural-language conflicts (descriptions, judgment rules). An LLM adapter in
    practice; its findings are warnings, never errors (ADR-0009)."""

    def conflicts(self, old: Domain | None, new: Domain, changed: list[str]) -> list[tuple[str, str]]: ...


# -- the pipeline -------------------------------------------------------------------------------
def change_check(new: Domain, old: Domain | None = None, *, events: EventStore | None = None,
                 nl: NLChecker | None = None, examples: int = 50,
                 roles_of: Callable[[dict[str, Any], str], tuple[str, ...]] | None = None) -> ChangeReport:
    """Run every check of `new` against `old` (None: the first version). `events` is the
    deployed environment's event store, for log replay and the in-flight check. `roles_of`
    resolves a past actor's roles (the Identity port); without it, an actor is assumed to have
    had every role the current version allowed for that action."""
    checks: dict[str, CheckResult] = {}
    checks["structural"] = _structural(new, old)
    structurally_ok = checks["structural"].ok
    if structurally_ok:
        checks["semantic"] = _semantic(new, old)
        checks["scenarios"] = _scenarios(new, old)
        checks["harness"] = _harness(new, examples)
    else:
        for name in ("semantic", "scenarios", "harness"):
            checks[name] = CheckResult(name, ran=False, note="the declaration has structural errors")
    if events is None:
        for name in ("log_replay", "in_flight"):
            checks[name] = CheckResult(name, ran=False, note="no event store (nothing deployed)")
    else:
        checks["in_flight"] = in_flight(new, events)
        checks["log_replay"] = log_replay(new, old, events, roles_of) if structurally_ok else \
            CheckResult("log_replay", ran=False, note="the declaration has structural errors")
    checks["nl"] = _nl(new, old, nl)
    return ChangeReport(new.domain, _diff(new, old), {n: checks[n] for n in CHECKS})


def check_commit(commits: Any, domain: str, commit_id: str, base: str | None = "merge-base", *,
                 events: EventStore | None = None, nl: NLChecker | None = None, examples: int = 50,
                 roles_of: Callable[[dict[str, Any], str], tuple[str, ...]] | None = None) -> ChangeReport:
    """Run the change check on a commit of a commit store, and record the result on the commit
    (ADR-0032): one record per check that ran, plus `change-check` for the whole. The base is
    the commit's merge base with `main` by default (ADR-0033: a branch is reviewed from there),
    or its first parent when the commit is already in `main`; None checks it as a first version."""
    c = commits.get(domain, commit_id)
    if base == "merge-base":
        main = commits.main(domain)
        base = commits.merge_base(domain, c.id, main.id) if main else None
        if base == c.id:
            base = c.parents[0] if c.parents else None
    old = commits.domain(domain, base) if base else None
    report = change_check(commits.domain(domain, c.id), old, events=events, nl=nl, examples=examples,
                          roles_of=roles_of)
    report.diff["from"], report.diff["to"] = base, c.id
    for name, res in report.checks.items():
        if res.ran:
            commits.record_check(domain, c.id, name, res.ok, res.summary(), base)
    commits.record_check(domain, c.id, "change-check", report.ok, report.summary(), base)
    return report


def _diff(new: Domain, old: Domain | None) -> dict[str, Any]:
    r = review_diff(review_elements(old) if old else {}, review_elements(new))
    bump = diff_interface(interface(old), interface(new)).bump if old else "initial"
    return {"changed": r.changed, "added": r.added, "removed": r.removed, "to_review": r.to_review,
            "interface_bump": bump}


def _structural(new: Domain, old: Domain | None) -> CheckResult:
    res = CheckResult("structural")
    before = {(i.code, i.where) for i in validate_domain(old)} if old else set()
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


def undecided_cells(d: Domain) -> list[str]:
    out = []
    for obj, tr in d.transitions.items():
        for state, row in tr.matrix.items():
            for action, cell in row.items():
                by_role = getattr(cell, "by_role", None) or {}
                if cell == "undecided" or "undecided" in by_role.values():
                    out.append(f"cell:{obj}.{state}.{action}")
    return out


def _semantic(new: Domain, old: Domain | None) -> CheckResult:
    from ..harness.world import grow_world
    res = CheckResult("semantic")
    unreach_new = grow_world(new).unreachable
    unreach_old = grow_world(old).unreachable if old and not _has_errors(old) else {}
    for obj, states in unreach_new.items():
        for s in states:
            newly = old is not None and s not in unreach_old.get(obj, []) and obj in old.transitions \
                and s in old.transitions[obj].matrix
            res.add("error" if newly else "warning", f"state:{obj}.{s}",
                    "no longer reachable from the examples" if newly else "not reachable from the examples")
    dead_old = set(dead_actions(old)) if old else set()
    for a in dead_actions(new):
        newly = old is not None and a in old.actions and a not in dead_old
        res.add("error" if newly else "warning", f"action:{a}",
                "no matrix cell allows it any more" if newly else "no matrix cell allows it")
    for c in undecided_cells(new):
        res.add("info", c, "undecided")
    return res


def _has_errors(d: Domain) -> bool:
    return any(i.severity == "error" for i in validate_domain(d))


def _scenarios(new: Domain, old: Domain | None) -> CheckResult:
    """Scenario regression: the current version's scenarios and the new ones, on the new model."""
    from ..harness.run import Harness
    res = CheckResult("scenarios")
    scenarios = {sc.id: sc for sc in new.scenarios}
    carried = [sc for sc in (old.scenarios if old else []) if sc.id not in scenarios]
    d = new.model_copy(update={"scenarios": list(new.scenarios) + carried})
    h = Harness(d, levels=("model",))
    passed = h.flows("model")
    for f in h.findings:
        sid = f.case.split("#")[0]
        origin = "a scenario the new version removed" if sid in {s.id for s in carried} else "scenario"
        res.add("error", f"scenario:{f.case}", f"{origin} fails: {f.detail.get('why')}")
    res.note = f"{passed}/{len(d.scenarios)} scenarios pass"
    return res


def _harness(new: Domain, examples: int) -> CheckResult:
    from ..harness import run_harness
    res = CheckResult("harness")
    report = run_harness(new, levels=("model",), explore_examples=examples, races=False)
    for f in report.findings:
        if f.kind == "flow":
            continue                                    # reported by the scenario check
        res.add("error", f"{f.kind}:{f.case}", _short(f.detail))
    cells = (report.coverage or {}).get("cells") or {}
    covered = (cells.get("covered") or {}).get("model", "?")
    res.note = f"{covered}/{cells.get('decided', '?')} decided cells covered at the model level"
    return res


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
               roles_of: Callable[[dict[str, Any], str], tuple[str, ...]] | None = None) -> CheckResult:
    """Re-decide every past action with the new model, in order, at its original time. The
    replayed store takes the recorded events, not the new ones, so one blocked action does
    not cascade into the rest of history."""
    res = CheckResult("log_replay")
    clock_at: list[datetime] = [EPOCH]
    interp = Interpreter(new, lambda: clock_at[0])
    replay = MemoryEventStore()

    def lookup(oid: str):
        evs = replay.read(oid)
        return (evs[0].aggregate, project(evs)) if evs else None

    history = [ev for _, evs in _domain_streams(events) for ev in evs if ev.kind == "domain"]
    history.sort(key=lambda e: (e.at or EPOCH, e.stream, e.version or 0))
    replayed = blocked = 0
    for ev in history:
        action = (ev.payload or {}).get("action")
        if action is not None and ev.actor is not None:
            replayed += 1
            clock_at[0] = ev.at or clock_at[0]
            cmd = _command(ev, new, old, roles_of)
            found = lookup(ev.stream)
            state = None if found is None else found[1]
            dec = interp.decide(cmd, state, lookup)
            when = ev.at.isoformat() if ev.at else "?"
            if not dec.outcome.ok:
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
    res.note = f"{replayed} past action(s) replayed; {blocked} would be blocked"
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
    elif kind == "system":
        roles = ("system",)
    else:                     # it succeeded then, so the actor held a role the old version allowed
        src = old if old is not None and action in old.actions else new
        a = src.actions.get(action)
        roles = tuple(r for r in (a.actor if a else []) if isinstance(r, str)) or tuple(src.roles)
    actor = Actor(ref.get("id"), kind, roles)
    principal = grant = None
    if ev.on_behalf_of:
        principal = Actor(ev.on_behalf_of.get("id"), ev.on_behalf_of.get("kind", "person"), roles)
        grant = Grant(ev.grant or "replay", frozenset(new.actions))
    return Command(actor, action, ev.stream, copy.deepcopy(ev.payload.get("params") or {}), at=ev.at,
                   on_behalf_of=principal, grant=grant, thread_id=ev.thread_id, run_id=ev.run_id,
                   causation=ev.causation)


def _nl(new: Domain, old: Domain | None, nl: NLChecker | None) -> CheckResult:
    if nl is None:
        return CheckResult("nl", ran=False, note="no natural-language checker configured")
    res = CheckResult("nl")
    changed = _diff(new, old)["to_review"]
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
    "undecided_cells",
]
