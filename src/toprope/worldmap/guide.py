"""The domain guide: a readable account of one domain, generated from its declaration.

It answers "how does this domain work, and what is made from it?" in the terms of
`docs/domain-model.md`: purpose, people and things, actions and everything each one connects
to, the transition matrix per object, the rules, the examples, and the generated surfaces.
It is a compile output, written next to `world-map.json` at preview. It is never edited by
hand, so it cannot drift from the declaration.
"""

from __future__ import annotations

from typing import Any

from ..decl.models import Action, ActorRule, ByRole, Deny, Domain, Target
from ..kernel import KERNEL

HUMAN, DECISION = "🔒", "📝"


def _cell(c: Any) -> str:
    if isinstance(c, Target):
        return f"→ `{c.to}`"
    if isinstance(c, Deny):
        return f"denied: {c.deny}"
    if isinstance(c, ByRole):
        return "; ".join(f"{r}: {_cell(v)}" for r, v in c.by_role.items())
    if c == "n/a":
        return "n/a"
    if c == "undecided":
        return "**undecided**"
    return f"→ `{c}`"


def _who(a: Action) -> str:
    out = []
    for r in a.actor:
        if isinstance(r, ActorRule):
            out.append(f"{r.role} (where `{r.where}`)" if r.where else r.role)
        else:
            out.append("the kernel" if r == KERNEL else r)
    return ", ".join(out)


def _param(name: str, p: Any) -> str:
    kind = p.type or (f"one of {', '.join(p.enum)}" if p.enum else f"a {p.ref}")
    return f"`{name}` ({kind}{', many' if p.many else ''}{', optional' if p.optional else ''})"


def _event(d: Domain, name: str, a: Action) -> str:
    from ..semantics.interpreter import _pascal
    obj = a.object_type
    return a.event or (f"{obj}Created" if a.creates else f"{obj}{_pascal(name)}")


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |"


def _doer(a: Action) -> str:
    """Who takes an action, in words: people by role, the kernel, or another domain."""
    who = []
    for r in a.actor:
        role = r if isinstance(r, str) else r.role
        if role == KERNEL:
            who.append("the kernel, automatically (a reply)")
        elif role == "system":
            who.append("the system (a handoff from another domain)")
        else:
            who.append(f"`{role}`" + (f" (where `{r.where}`)" if not isinstance(r, str) and r.where else ""))
    return ", ".join(who)


def _command(d: Domain, n: str, a: Action) -> str:
    args = " ".join(f"--{p.replace('_', '-')} {p.upper()}" for p, spec in a.params.items() if not spec.optional)
    target = "NEW_ID" if a.creates else "ID"
    return f"`toprope-run --domain {d.domain}.domain.yaml {n} {target}{(' ' + args) if args else ''}`"


def _step(d: Domain, n: str, a: Action, to: str | None) -> str:
    flags = " — **a person only**" if a.requires == "human" else ""
    flags += " — recorded as a decision" if a.records_decision else ""
    starts = [f"starts kernel `{e.call}`, answered by `{e.reply}`" for e in a.effects if e.call]
    starts += [f"hands over to {h.to.domain}.`{h.to.action}`" for h in d.handoffs.values() if h.when.action == n]
    needs = [p.reason for p in a.preconditions]
    line = f"- **{n}** by {_doer(a)}{flags}" + (f" → `{to}`" if to else "")
    if needs:
        line += ". Needs: " + " ".join(r.rstrip(".") + "." for r in needs).rstrip(".")
    if starts:
        line += f". Then {'; '.join(starts)}"
    is_reply = any((r if isinstance(r, str) else r.role) in (KERNEL, "system") for r in a.actor)
    return line + ("" if is_reply else f". Run: {_command(d, n, a)}")


def _how_to_work(d: Domain) -> list[str]:
    """Who does what, stage by stage, in the order a thing moves through its stages."""
    L = ["## How to work in this domain", "",
         ("Generated from the actions, their actors, the matrix and the kernel calls: for each thing, "
          "how it comes to exist, then what can happen in each stage and who does it. "
          "Steps marked **a person only** are never taken by an agent."), ""]
    done: set[str] = set()
    for obj, tr in sorted(d.transitions.items()):
        L += [f"### {obj}", ""]
        for n, a in d.actions.items():
            if a.creates == obj:
                L += [_step(d, n, a, tr.initial)]
                done.add(n)
        L += [""]
        order, todo = [], [tr.initial]
        while todo:
            st = todo.pop(0)
            if st in order or st not in tr.matrix:
                continue
            order.append(st)
            for c in tr.matrix[st].values():
                to = getattr(c, "to", None) or (c if isinstance(c, str) and c not in ("n/a", "undecided") else None)
                if to:
                    todo.append(to)
        order += [s for s in tr.matrix if s not in order]
        for st in order:
            steps = []
            for n, a in d.actions.items():
                if a.target != obj:
                    continue
                c = tr.matrix[st].get(n, "undecided")
                to = c.to if isinstance(c, Target) else (c if isinstance(c, str) and c not in ("n/a", "undecided") else None)
                if to is not None or isinstance(c, ByRole):
                    steps.append(_step(d, n, a, to if to != st else None))
                    done.add(n)
            L += ([f"**In `{st}`:**", ""] + steps if steps else [f"**In `{st}`:** nothing more happens (final)."]) + [""]
    rest = [(n, a) for n, a in d.actions.items() if n not in done]
    if rest:
        L += ["### Other actions", ""] + [_step(d, n, a, None) for n, a in rest] + [""]
    return L


def build_domain_guide(d: Domain, harness: dict[str, Any] | None = None) -> str:
    """`harness` is a harness report as JSON; without it, coverage is not reported."""
    L: list[str] = [f"# Domain guide: `{d.domain}` (version {d.version})", "",
                    "_Generated from the declaration at build time. Do not edit: change the declaration._", ""]

    if d.purpose is not None:
        p = d.purpose
        L += ["## Purpose", "", p.problem, ""]
        if p.success_metric is not None:
            L += [f"**Success metric:** {p.success_metric.name} ({p.success_metric.direction} is better)", ""]
        if p.announcement:
            L += [f"> {p.announcement}", ""]

    L += ["## People and things", ""]
    people = ", ".join(f"`{r}`" + (f" ({', '.join(d.world.actors[r])})" if d.world.actors.get(r) else "")
                       for r in d.roles) or "none"
    L += [f"**Roles:** {people}. Agents act only on a person's behalf, with a grant.", ""]
    for name, o in sorted(d.objects.items()):
        tr = d.transitions.get(name)
        stages = f" Stages: {', '.join(f'`{s}`' for s in tr.matrix)} (starts `{tr.initial}`)." if tr else ""
        L += [f"- **{name}**" + (f": {o.description}" if o.description else "") + (f".{stages}" if not o.description and stages else stages)]
        facts = [f"`{k}` ({v.type or 'one of ' + ', '.join(v.enum or [])}{', optional' if v.optional else ''})"
                 for k, v in o.properties.items() if not tr or k != tr.field]
        if facts:
            L += [f"  - facts: {', '.join(facts)}"]
    L += [""]
    if d.links:
        L += ["**Links** (read like a field of the `from` object):", "",
              _row(["link", "from → to", "cardinality", "required"]), _row(["---"] * 4)]
        for n, link in sorted(d.links.items()):
            L += [_row([f"`{link.from_}.{n}`", f"{link.from_} → {link.to}", link.cardinality,
                        "yes" if link.required else "no"])]
        L += [""]

    L += ["## Actions", "", f"{HUMAN} only a person may take it · {DECISION} recorded as a decision", "",
          _row(["action", "who", "on", "needs first", "changes", "starts", "event"]), _row(["---"] * 7)]
    for n, a in d.actions.items():
        on = f"creates **{a.creates}**" if a.creates else f"**{a.target}**"
        if a.params:
            on += "; params " + ", ".join(_param(k, v) for k, v in a.params.items())
        needs = "; ".join(f"`{p.id}`: {p.reason}" for p in a.preconditions) or "—"
        sets = [f"`{k}` ← `{v}`" for e in a.effects if e.set for k, v in e.set.items()]
        changes = ("the stage (per the matrix); " if a.target in d.transitions else "") + (", ".join(sets) or "")
        starts = [f"kernel `{e.call}` → `{e.reply}`" for e in a.effects if e.call]
        starts += [f"handoff `{h}` → {x.to.domain}.{x.to.action}" for h, x in d.handoffs.items() if x.when.action == n]
        flags = (f" {HUMAN}" if a.requires == "human" else "") + (f" {DECISION}" if a.records_decision else "")
        L += [_row([f"`{n}`{flags}", _who(a), on, needs, changes.strip("; ") or "—", "; ".join(starts) or "—",
                    f"`{_event(d, n, a)}`"])]
    L += [""]

    if d.transitions:
        L += ["## Transitions", "", ("For each stage: may the action happen, and where does it lead? "
                                     "A missing cell is undecided; nothing is ever silently allowed."), ""]
        for obj, tr in sorted(d.transitions.items()):
            acts = [n for n, a in d.actions.items() if a.target == obj]
            L += [f"### {obj} (`{tr.field}`)", ""]
            if acts:
                L += [_row(["stage"] + [f"`{a}`" for a in acts]), _row(["---"] * (len(acts) + 1))]
                for state, row in tr.matrix.items():
                    L += [_row([f"`{state}`"] + [_cell(row.get(a, "undecided")) for a in acts])]
            L += [""]
        undecided = [f"{obj}.{s}.{a}" for obj, tr in d.transitions.items() for s, row in tr.matrix.items()
                     for a, x in d.actions.items() if x.target == obj and _cell(row.get(a, "undecided")) == "**undecided**"]
        if undecided:
            L += [f"**Undecided cells ({len(undecided)}):** " + ", ".join(f"`{u}`" for u in undecided), ""]

    if d.invariants:
        L += ["## Always true (invariants)", ""]
        L += [f"- **{i.id}** on {i.on}: {i.reason}" for i in d.invariants] + [""]

    if d.rules:
        from ..decl.models import RuleCheck
        from ..decl.rules import reaches
        L += ["## Who may bring about an outcome (rules)", "",
              "Every action that reaches the outcome is held to the rule, an action added later too.", ""]
        for rid, r in d.rules.items():
            who = ("a person" if r.requires == "human" else
                   f"`{r.requires.check}`" if isinstance(r.requires, RuleCheck) else
                   " or ".join(f"`{x}`" for x in r.requires.roles))
            tr = d.transitions.get(r.on.split(".", 1)[0])
            froms = (list(tr.matrix) if tr else []) + [None]
            by = sorted({a for a in d.actions if any(r.on in reaches(d, a, f) for f in froms)})
            L += [f"- **{rid}** on `{r.on}`: only {who}. {r.reason}"
                  + (f" Covers: {', '.join(f'`{a}`' for a in by)}." if by else " No action reaches it yet.")]
        L += [""]

    if d.world.fixtures or d.scenarios:
        L += ["## Examples and scenarios", ""]
        if d.world.fixtures:
            L += [f"- {len(d.world.fixtures)} example object(s): " + ", ".join(
                f"{next(iter(f))} `{next(iter(f.values())).get('id')}`" for f in d.world.fixtures)]
        L += [f"- scenario `{s.id}`: {len(s.steps)} step(s)" for s in d.scenarios] + [""]

    if d.handoffs:
        L += ["## Handoffs", ""]
        L += [f"- `{n}`: after `{h.when.action}`, calls {h.to.domain}.`{h.to.action}`" for n, h in d.handoffs.items()] + [""]

    L += _how_to_work(d)
    replies = [n for n, a in d.actions.items() if KERNEL in [r if isinstance(r, str) else r.role for r in a.actor]]
    L += ["## What is generated", "",
          (f"- **Command line** `toprope-run --domain {d.domain}.domain.yaml ...`: one subcommand per action, "
           "with the same rules as every other surface (ADR-0036), plus `get`, `history`, `allowed` and `guide`."),
          (f"- **MCP server** `toprope:{d.domain}`: one tool per action ({len(d.actions)}), plus `get_object`, "
           "`history`, `attempts`, `allowed_actions`, `describe_domain`, `world_map` and `how_to_reach`."
           + (f" Kernel replies ({', '.join(f'`{r}`' for r in replies)}) are tools too, but only the kernel "
              "may take them." if replies else "")),
          (f"- **Events**: one per action ({', '.join(sorted({f'`{_event(d, n, a)}`' for n, a in d.actions.items()}))}); "
           "the current state is the events replayed in order."),
          "- **World map** (`world-map.json`): every object, link, stage and (stage, action) edge."]
    if harness:
        cells = (harness.get("coverage") or {}).get("cells") or {}
        covered = cells.get("covered") or {}
        L += [f"- **Harness**: {'passes' if harness.get('ok') else 'fails'}; decided cells covered per level: "
              + ", ".join(f"{lv} {n}/{cells.get('decided', '?')}" for lv, n in covered.items())
              + f"; {len(harness.get('findings') or [])} finding(s)."]
    else:
        L += ["- **Harness**: generated from the matrix, invariants, examples and scenarios (run it to see coverage)."]
    return "\n".join(L).rstrip() + "\n"


__all__ = ["build_domain_guide"]
