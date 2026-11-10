"""Replay a TLC counterexample on the interpreter and judge it (ADR-0043, Decision 3).

TLC prints a violated invariant's trace as states; the exported module's `last` variable names
each step: `<<action, role, instance id, <<<<param, tagged value>>, ...>>>>`. The steps are taken
again, in order, on the model level (`ModelSurface`) from the same fixtures, by the same actors.

- Every step but the last is `ok` and the last is `invariant-guard` for the same invariant: the
  counterexample is **reproduced**. If the harness also reports that invariant broken, it is
  the declaration's break, already reported (`known`); otherwise a **harness gap**.
- Anything else: a **model mismatch**. The exporter, or the interpreter, does not mean what the
  declaration says.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from ..decl.models import Domain
from ..errors import fixed
from ..semantics import refusals

KNOWN, GAP, MISMATCH = "known", "harness gap", "model mismatch"


@dataclass
class Step:
    action: str
    role: str
    target: str
    params: dict[str, Any]


# -- reading TLC's trace -----------------------------------------------------------------------
_TOKEN = re.compile(r'\s*(<<|>>|,|"(?:[^"\\]|\\.)*"|-?\d+|TRUE|FALSE)')


def parse_value(text: str) -> Any:
    """A TLA+ value made of sequences, strings, integers and booleans, as TLC prints it."""
    pos, out = 0, []

    def token() -> str:
        nonlocal pos
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(fixed(f"cannot read TLC value at {text[pos:pos + 40]!r}",
                                   "give the trace as TLC prints it, one state per value"))
        pos = m.end()
        return m.group(1)

    def value(tok: str) -> Any:
        if tok == "<<":
            items: list[Any] = []
            tok = token()
            while tok != ">>":
                items.append(value(tok))
                tok = token()
                if tok == ",":
                    tok = token()
            return tuple(items)
        if tok.startswith('"'):
            return bytes(tok[1:-1], "utf-8").decode("unicode_escape")
        if tok in ("TRUE", "FALSE"):
            return tok == "TRUE"
        return int(tok)

    out.append(value(token()))
    if text[pos:].strip():
        raise ValueError(fixed(f"trailing text after a TLC value: {text[pos:pos + 40]!r}",
                               "give the trace as TLC prints it, one state per value"))
    return out[0]


def _untag(v: Any) -> Any:
    tag = v[0]
    if tag == "n":
        return None
    if tag == "s":
        s = v[1]
        return bytes.fromhex(s[2:]).decode() if s.startswith("u:") else s
    if tag in ("i", "b"):
        return v[1]
    if tag == "l":
        return [_untag(x) for x in v[1]]
    raise ValueError(fixed(f"a param value TLC cannot hold: {v!r}",
                           "replay only traces of Toprope's own TLA export, whose params it can hold"))


def parse_trace(tlc_output: str) -> tuple[str | None, list[Step]]:
    """The violated invariant (its TLA+ operator name) and the steps of TLC's trace."""
    m = re.search(r"Invariant (\S+) is violated", tlc_output)
    inv = m.group(1) if m else None
    steps: list[Step] = []
    for block in re.split(r"\n(?=State \d+:)", tlc_output):
        if not block.startswith("State "):
            continue
        lm = re.search(r"/\\ last = (.*?)(?=\n/\\ |\n\n|\Z)", block, re.DOTALL)
        if not lm:
            continue
        last = parse_value(" ".join(lm.group(1).split()))
        if last == ("init",):
            continue
        action, role, target, params = last
        steps.append(Step(action, role, target, {k: _untag(v) for k, v in params}))
    return inv, steps


# -- replaying ---------------------------------------------------------------------------------
def replay(d: Domain, steps: list[Step]) -> list[dict[str, Any]]:
    """Take the steps on the model level, from the fixtures; return each outcome."""
    from ..harness.run import NOW
    from ..harness.surfaces import ModelSurface
    from . import model_actors
    actors = model_actors(d)
    s = ModelSurface(d, lambda: NOW)
    for fx in d.world.fixtures:
        for obj, data in fx.items():
            s.seed(obj, copy.deepcopy(data))
    out = []
    for k, st in enumerate(steps):
        o = s.do(actors[st.role], st.action, st.target, dict(st.params), f"tla{k}")
        out.append({"action": st.action, "role": st.role, "target": st.target, "params": st.params,
                    "status": o.get("status"), "code": o.get("code"), "reason": o.get("reason")})
    return out


def judge(d: Domain, invariant_op: str | None, steps: list[Step], harness_broken: set[str]) -> dict[str, Any]:
    """The verdict on one counterexample. `harness_broken` holds the invariant ids the harness
    reports broken for this declaration."""
    inv = next((i for i in d.invariants if invariant_op == "Inv_" + re.sub(r"[^A-Za-z0-9]", "_", i.id)), None)
    if inv is None or not steps:
        return {"verdict": MISMATCH, "invariant": invariant_op,
                "why": "no invariant or no step to replay" if inv is None or not steps else ""}
    outcomes = replay(d, steps)
    *before, last = outcomes
    reproduced = (all(o["status"] == "ok" for o in before) and last["code"] == "invariant-guard"
                  and last["reason"] == refusals.invariant(inv.reason, inv.check, d))
    if not reproduced:
        bad = next((o for o in outcomes if o["status"] != "ok"), last)
        return {"verdict": MISMATCH, "invariant": inv.id, "steps": outcomes,
                "why": f"step {outcomes.index(bad) + 1} ({bad['action']} by {bad['role']} on {bad['target']}) "
                       f"gave {bad['status']} {bad['code'] or ''} on the interpreter"}
    return {"verdict": KNOWN if inv.id in harness_broken else GAP, "invariant": inv.id, "steps": outcomes}


def harness_broken(d: Domain) -> set[str]:
    """The invariants the harness reports broken (cell tests, exploration), model level."""
    from ..harness import run_harness
    r = run_harness(d, levels=("model",), races=False)
    out = set()
    for f in r.findings:
        if f.kind == "invariant":
            det = f.detail
            inv = det.get("invariant") or ((det.get("observed") or {}).get("reason"))
            out.add(next((i.id for i in d.invariants
                          if inv in (i.id, i.reason, refusals.invariant(i.reason, i.check, d))), inv))
        elif f.kind == "exploration":
            out.add(f.detail.get("invariant"))
    return out


__all__ = ["GAP", "KNOWN", "MISMATCH", "Step", "harness_broken", "judge", "parse_trace", "parse_value", "replay"]
