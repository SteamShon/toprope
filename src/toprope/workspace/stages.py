"""Staged interview (ADR-0025): the declaration is built in the order its parts depend on.
Each stage asks one bundle of questions, takes the owner's answers at once, and reports how
far the domain has come. The current stage is the first one that is not done, so a later
change that breaks an earlier stage sends the interview back to it.

  sources → purpose → cast (roles, objects, links) → actions → transitions → invariants
          → world (fixtures, scenarios) → handoffs → review (confirmations, glossary)

Within a stage, conflicts come first, then the questions for what is missing. In
transitions, ADR-0014's defaults, grouped rows, priorities and stop rule still apply.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..decl import Domain

if TYPE_CHECKING:
    from . import Question, Workspace


@dataclass(frozen=True)
class Stage:
    name: str
    title: str
    goal: str
    paths: tuple[str, ...]      # top-level keys of the declaration this stage fills
    optional: bool = False      # the owner may say there is nothing here (skip_stage)


STAGES: tuple[Stage, ...] = (
    Stage("sources", "Sources", "Where the raw material lives: paths or links to code, records "
          "and transcripts.", ()),
    Stage("purpose", "Purpose", "The problem, one success metric, and a two-sentence announcement.",
          ("purpose",)),
    Stage("cast", "People and things", "Who takes part (roles), what the work tracks (objects and "
          "their key facts), and how those things relate (links).", ("roles", "objects", "links")),
    Stage("actions", "Actions", "What each role does to which thing, what must be true first, and "
          "what it changes.", ("actions",)),
    Stage("transitions", "Transitions", "The stages each tracked thing goes through, and what each "
          "action does in each stage.", ("transitions",)),
    Stage("invariants", "Invariants", "What must always be true, however things got there.",
          ("invariants",), optional=True),
    Stage("world", "World and scenarios", "Realistic examples of everything, and flows that test "
          "the world, including a refused step.", ("world", "scenarios")),
    Stage("handoffs", "Handoffs", "What this domain hands to another domain, when, and with what.",
          ("handoffs",), optional=True),
    Stage("review", "Review", "Confirm what is right, and define the words a newcomer would misread.",
          ("glossary",)),
)
BY_NAME = {s.name: s for s in STAGES}


def _qid(kind: str, subject: str) -> str:
    return hashlib.sha1(f"{kind}:{subject}".encode()).hexdigest()[:10]


class Plan:
    """The stage state of one draft. Built fresh for each call; it holds no state of its own."""

    def __init__(self, ws: Workspace, doc: dict[str, Any], d: Domain | None,
                 issues: list[Any], attempts: dict[str, int]):
        self.ws, self.doc, self.d, self.issues, self.attempts = ws, doc, d, issues, attempts
        self.skipped = {e["stage"]: e.get("reason") for e in ws._read(ws.log_path) if e.get("kind") == "skip"}

    # -- what each stage needs ---------------------------------------------------------------
    def errors_in(self, stage: Stage) -> list[Any]:
        return [i for i in self.issues if i.severity == "error"
                and any(i.where == p or i.where.startswith(p + ".") for p in stage.paths)]

    def done(self, stage: Stage) -> bool:
        d = self.d
        if d is None:
            return False
        if self.errors_in(stage):
            return False
        if stage.optional and stage.name in self.skipped:
            return True
        n = stage.name
        if n == "sources":
            return any(self.ws.chunks(s) for s in self.ws.sources)
        if n == "purpose":
            p = d.purpose
            return bool(p and p.problem and p.success_metric and p.announcement)
        if n == "cast":
            return bool(d.roles and d.objects)
        if n == "actions":
            return bool(d.actions)
        if n == "transitions":
            return not self.untracked() and bool(d.transitions) and self.ws._stop(d, self.attempts)["stop"]
        if n == "invariants":
            return bool(d.invariants)
        if n == "world":
            return bool(d.world.fixtures and d.scenarios)
        if n == "handoffs":
            return bool(d.handoffs)
        if n == "review":   # the last stage: everything before it is done, and nothing is unconfirmed
            return all(self.done(x) for x in STAGES[:-1]) and not self.ws._proposed(self.doc)
        return False

    def untracked(self) -> list[str]:
        """Objects that actions change but that have no stages yet."""
        d = self.d
        targets = {a.target for a in d.actions.values() if a.target and a.creates is None}
        return sorted(t for t in targets if t in d.objects and t not in d.transitions)

    def current(self) -> Stage | None:
        return next((s for s in STAGES if not self.done(s)), None)

    # -- the bundle for a stage ---------------------------------------------------------------
    def bundle(self, stage: Stage) -> list[Question]:
        from . import Question
        out: list[Question] = []

        def q(kind: str, subject: str, text: str, decides: list[str], priority: float = 0,
              skip: str | None = None) -> None:
            from . import Choice
            qid = _qid(kind, subject)
            from . import choice_id
            choices = [Choice(choice_id(qid, 1, [], skip), f"nothing, for any of them: skip the whole {skip} stage",
                              [], False, "", skip)] if skip else []
            out.append(Question(qid, kind, text, decides, priority, choices))

        for i in self.errors_in(stage):
            q("conflict", f"{i.code}@{i.where}", f"The draft has a conflict at {i.where}: {i.message}. "
              "Which is right?", [i.where], 1e6)
        d = self.d
        n = stage.name
        if n == "sources":
            q("sources", "where", "Where does the material for this domain live? Give paths in this "
              "workspace or links (a link is fetched once into a snapshot). Say which ones must never "
              "go to a hosted model (local-only).", ["sources"])
        elif d is None:
            pass
        elif n == "purpose":
            p = d.purpose
            if not (p and p.problem):
                q("purpose", "problem", "What problem does this domain solve, and for whom?", ["purpose.problem"])
            if not (p and p.success_metric):
                q("purpose", "metric", "Which one metric shows it is solved, and should it go up or down?",
                  ["purpose.success_metric"])
            if not (p and p.announcement):
                q("purpose", "announcement", "How would you announce it when it works, in two sentences?",
                  ["purpose.announcement"])
        elif n == "cast":
            if not d.roles:
                q("cast", "roles", "Who takes part? For each kind of person, agent or system involved: "
                  "its role, in a few words.", ["roles"])
            if not d.objects:
                q("cast", "objects", "What does the work keep track of? For each thing: what it is, its "
                  "key facts, and whether it moves through stages.", ["objects"])
            if d.objects and not d.links and len(d.objects) > 1:
                q("cast", "links", "How do these things relate? For each pair: which refers to which, "
                  "one or many, and whether it is required.", ["links"])
            linked = {e for l in d.links.values() for e in (l.from_, l.to)}
            for name, o in d.objects.items():
                if not o.description:
                    q("cast", f"describe:{name}", f"What is a {name}, in your words?", [f"objects.{name}"])
                if len(d.objects) > 1 and d.links and name not in linked:
                    q("cast", f"relate:{name}", f"How does a {name} relate to the other things?", ["links"])
        elif n == "actions":
            have = {next(iter(f)) for f in d.world.fixtures if isinstance(f, dict) and f}
            for name, o in d.objects.items():       # examples first (ADR-0049, B2): a real case, then rules
                if name not in have and o.properties:
                    facts = ", ".join(list(o.properties)[:4])
                    q("example", name, f"Before any rule: tell me about one real {name} from your work. What "
                      f"were its {facts}, and what happened to it next? Use made-up names and numbers for "
                      "people, accounts and cards. (It becomes an example the checks run on, and the "
                      "questions after this use it.)", ["world.fixtures"], 2)
            if not d.actions:
                q("actions", "all", "What does each role do, to which thing? For each action: what must be "
                  "true first, and what it changes.", ["actions"])
            used = {r if isinstance(r, str) else r.role for a in d.actions.values() for r in a.actor}
            for role in d.roles:
                if role not in used:
                    q("actions", f"role:{role}", f"What does the {role} do here, if anything?", ["actions"])
            touched = {a.target for a in d.actions.values()} | {a.creates for a in d.actions.values()}
            referenced = {l.to for l in d.links.values()}
            for obj in d.objects:
                if obj not in touched and obj not in referenced:
                    q("actions", f"object:{obj}", f"How does a {obj} come to exist, and what changes it?",
                      ["actions"])
        elif n == "transitions":
            for obj in self.untracked():
                q("transitions", f"stages:{obj}", f"What stages does a {obj} go through? Where does it "
                  "start, and which stages are final?", [f"transitions.{obj}"], 1e5)
            out += self.ws._cell_questions(d, self.attempts)
        elif n == "invariants":
            for obj in sorted(d.transitions):
                q("invariants", obj, f"What must always be true about a {obj}, in every stage, however it got "
                  "there? (If nothing, say so.)", ["invariants"], skip="invariants")
        elif n == "world":
            if not d.world.fixtures:
                q("world", "fixtures", "Give realistic examples: at least one of each thing, with its key "
                  "facts. If you can, one in each stage.", ["world.fixtures"])
            if not d.world.actors:
                q("world", "actors", "Who are typical people for each role? Names are enough.", ["world.actors"])
            if not d.scenarios:
                q("world", "scenarios", "Walk through one typical flow from start to finish, and one where a "
                  "step is refused. Who does what, and what should happen?", ["scenarios"])
        elif n == "handoffs":
            q("handoffs", "all", "Does this domain hand its result to another domain? If so: which action "
              "triggers it, which domain and action receive it, and what it carries. (If not, say so.)",
              ["handoffs"], skip="handoffs")
        elif n == "review":
            proposed = self.ws._proposed(self.doc)
            if proposed:
                q("confirm", ",".join(sorted(proposed))[:200], f"{len(proposed)} drafted elements are not "
                  "confirmed yet. Review them and confirm the ones that are right.", sorted(proposed), 1)
            if not d.glossary:
                q("review", "glossary", "Which words here would a newcomer misread? Define each in a sentence.",
                  ["glossary"])
        out.sort(key=lambda x: (-x.priority, x.id))
        return out

    # -- progress -----------------------------------------------------------------------------
    def progress(self) -> list[dict[str, Any]]:
        cur = self.current()
        out = []
        for s in STAGES:
            done = self.done(s)
            status = ("skipped" if done and s.name in self.skipped and s.optional else
                      "done" if done else "current" if s is cur else "todo")
            out.append({"stage": s.name, "title": s.title, "status": status, **self._counts(s)})
        return out

    def _counts(self, s: Stage) -> dict[str, Any]:
        d = self.d
        if d is None:
            return {}
        n = s.name
        if n == "sources":
            return {"sources": len(self.ws.sources), "with_content": sum(1 for x in self.ws.sources if self.ws.chunks(x))}
        if n == "purpose":
            p = d.purpose
            return {"filled": [k for k in ("problem", "success_metric", "announcement") if p and getattr(p, k)]}
        if n == "cast":
            return {"roles": len(d.roles), "objects": len(d.objects), "links": len(d.links)}
        if n == "actions":
            return {"actions": len(d.actions)}
        if n == "transitions":
            cells = undecided = 0
            for obj, tr in d.transitions.items():
                acts = [a for a, x in d.actions.items() if x.target == obj and x.creates is None]
                for st in tr.matrix:
                    for a in acts:
                        cells += 1
                        undecided += tr.matrix[st].get(a, "undecided") == "undecided"
            return {"objects_with_stages": len(d.transitions), "cells": cells, "undecided": undecided}
        if n == "invariants":
            return {"invariants": len(d.invariants)}
        if n == "world":
            return {"fixtures": len(d.world.fixtures), "scenarios": len(d.scenarios)}
        if n == "handoffs":
            return {"handoffs": len(d.handoffs)}
        if n == "review":
            return {"proposed": len(self.ws._proposed(self.doc)), "glossary": len(d.glossary)}
        return {}


__all__ = ["BY_NAME", "STAGES", "Plan", "Stage"]
