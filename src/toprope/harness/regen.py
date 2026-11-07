"""The regeneration check (ADR-0028): a composition is served from its declarations and the
kernel alone, its harness passes at every level, regenerating everything from the files gives
the same results, and every declared kernel call runs end to end.

1. Load the composition from disk, check it, and run every member's harness (model,
   Execution, and MCP against the server generated from the declaration).
2. Regenerate: load everything again from disk into fresh objects, and run again.
3. The two runs must agree (findings and coverage), and both must pass.
4. Effects end to end: in a fresh assembled system with a recording kernel, each action that
   calls a kernel service is taken once where the harness expects it to succeed. Its call
   must be resolved, and its reply must be accepted (a denied reply drops the result).
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


def effects_end_to_end(path: Path) -> list[dict[str, Any]]:
    from ..compose import assemble, load_composition
    from ..handoff import Outbox
    from ..kernel.services import RecordingKernel
    from ..store import MemoryEventStore
    from .surfaces import _Identities
    c = load_composition(path)
    out = []
    for name, d in sorted(c.domains.items()):
        callers = [(n, a) for n, a in d.actions.items() if any(e.call for e in a.effects)]
        if not callers:
            continue
        h = Harness(d, levels=("model",))
        cases = [x for x in h.planner.cases() if x.expect.get("status") == "ok" and not x.gap]
        for action, a in callers:
            case = next((x for x in cases if x.action == action), None)
            if case is None:
                out.append({"domain": name, "action": action, "ok": False,
                            "why": "no world instance where the harness expects it to succeed"})
                continue
            ids = _Identities()
            kernel = RecordingKernel()
            exs = assemble(c, {n: MemoryEventStore() for n in c.domains}, ids, services=kernel)
            for ex in exs.values():
                ex.seed_world()
            ex = exs[name]
            for obj, data in h.world.fixtures:
                ex.seed(obj, copy.deepcopy(data))
            oid = f"{case.instance.data['id']}~e2e" if case.instance else f"{case.obj}~e2e"
            if case.instance:
                ex.seed(case.obj, {**copy.deepcopy(case.instance.data), "id": oid})
            actor = h.world.actors[case.role]
            if actor.kind == "system":
                o = ex.receive_kernel_reply("e2e", action, oid, case.params)
            else:
                o = ex.submit(ids.add(actor), action, oid, case.params, "e2e")
            results = [{"service": f["kernel"], "resolution": f["resolution"], "reply": f["reply_status"]}
                       for f in Outbox(ex).followed(oid) if "kernel" in f]
            effects = results
            # A reply that is denied or rejected drops the service's result: the wiring is broken.
            ok = o.ok and bool(effects) and all(r["resolution"] and r["reply"] == "ok" for r in results)
            out.append({"domain": name, "action": action, "ok": ok, "outcome": o.status,
                        "calls": [s for s, _ in kernel.calls], "effects": results})
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
