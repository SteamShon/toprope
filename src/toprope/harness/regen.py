"""The regeneration check (ADR-0028): a composition is served from its declarations and the
kernel alone, its harness passes at every level, regenerating everything from the files gives
the same results, and every declared kernel call runs end to end.

1. Load the composition from disk, check it, and run every member's harness (model,
   Execution, and MCP against the server generated from the declaration).
2. Regenerate: load everything again from disk into fresh objects, and run again.
3. The two runs must agree (findings and coverage), and both must pass.
4. Effects end to end: in a fresh assembled system with a recording kernel, each action that
   calls a kernel service is taken where the harness expects it to succeed, on each such
   instance until one works. Its call must be resolved, and its reply must be accepted (a
   denied reply drops the result).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .run import DEFAULT_LEVELS, Harness


def _normal(report: dict[str, Any]) -> dict[str, Any]:
    return {"ok": report["ok"], "findings": report["findings"], "coverage": report["coverage"]}


def _run(path: Path, levels, examples) -> tuple[list[Any], dict[str, Any]]:
    from ..compose import check_composition, load_composition
    c = load_composition(path)
    issues = check_composition(c)
    reports = {} if issues else {n: Harness(d, levels=levels).run(explore_examples=examples, races=False).to_json()
                                 for n, d in sorted(c.domains.items())}
    return issues, reports


def _one(c, h, name: str, action: str, case, data: dict[str, Any] | None) -> dict[str, Any]:
    """Take `action` once on the case's instance, in a fresh assembled system with a recording kernel."""
    from ..compose import assemble
    from ..handoff import Outbox, effect_id
    from ..kernel.services import RecordingKernel
    from ..store import MemoryEventStore
    from .surfaces import _Identities
    ids = _Identities()
    kernel = RecordingKernel()
    exs = assemble(c, {n: MemoryEventStore() for n in c.domains}, ids, services=kernel)
    for ex in exs.values():
        ex.seed_world()
    ex = exs[name]
    for obj, fixture in h.world.fixtures:
        ex.seed(obj, copy.deepcopy(fixture))
    oid = f"{data['id']}~e2e" if data else f"{case.obj}~e2e"
    if data:
        ex.seed(case.obj, {**copy.deepcopy(data), "id": oid})
    actor = h.world.actors[case.role]
    if actor.kind == "system":
        o = ex.receive_kernel_reply("e2e", action, oid, case.params)
    else:
        o = ex.submit(ids.add(actor), action, oid, case.params, "e2e")
    effects = [e for e in ex.history(oid) if e.type == "EffectRequested"]
    results = []
    for e in effects:
        res = Outbox(ex).resolution(effect_id(e), "effect")
        results.append({"service": e.payload["service"], "resolution": res.type if res else None,
                        "reply": res.payload.get("status") if res else None})
    # A reply that is denied or rejected drops the service's result: the wiring is broken.
    ok = o.ok and bool(effects) and all(r["resolution"] and r["reply"] == "ok" for r in results)
    return {"domain": name, "action": action, "ok": ok, "outcome": o.status,
            "instance": data["id"] if data else None,
            "calls": [s for s, _ in kernel.calls], "effects": results}


def _instances(h, d, cases):
    """Each case's own instance, then the other fixtures of its type in the same stage."""
    for case in cases:
        if case.instance is None:
            yield case, None
            continue
        yield case, case.instance.data
        t = d.transitions.get(case.obj)
        field = t.field if t else None
        for obj, data in h.world.fixtures:
            if obj == case.obj and data.get("id") != case.instance.data.get("id") \
                    and (field is None or data.get(field) == case.instance.data.get(field)):
                yield case, data


def effects_end_to_end(path: Path) -> list[dict[str, Any]]:
    from ..compose import load_composition
    c = load_composition(path)
    out = []
    for name, d in sorted(c.domains.items()):
        callers = [(n, a) for n, a in d.actions.items() if any(e.call for e in a.effects)]
        if not callers:
            continue
        h = Harness(d, levels=("model",))
        cases = [x for x in h.planner.cases() if x.expect.get("status") == "ok" and not x.gap]
        for action, _a in callers:
            tried = [x for x in cases if x.action == action]
            if not tried:
                out.append({"domain": name, "action": action, "ok": False,
                            "why": "no world instance where the harness expects it to succeed"})
                continue
            # The wiring works when one expected success runs end to end. Another instance may
            # rightly refuse a particular result (an invariant on that instance), so each is tried.
            runs = []
            for case, data in _instances(h, d, tried):
                runs.append(_one(c, h, name, action, case, data))
                if runs[-1]["ok"]:
                    break
            out.append(next((r for r in runs if r["ok"]), runs[0]) | {"tried": len(runs)})
    return out


def regen_check(path: str | Path, levels: tuple[str, ...] = DEFAULT_LEVELS, examples: int = 50) -> dict[str, Any]:
    path = Path(path)
    issues, first = _run(path, levels, examples)
    if issues:
        return {"ok": False, "issues": [f"{i.code} at {i.where}: {i.message}" for i in issues]}
    _, second = _run(path, levels, examples)
    same = {n: _normal(r) for n, r in first.items()} == {n: _normal(r) for n, r in second.items()}
    effects = effects_end_to_end(path)
    ok = same and all(r["ok"] for r in first.values()) and all(e["ok"] for e in effects)
    return {"ok": ok, "same_after_regenerating": same,
            "members": {n: {"ok": r["ok"], "findings": len(r["findings"])} for n, r in first.items()},
            "effects": effects}


__all__ = ["effects_end_to_end", "regen_check"]
