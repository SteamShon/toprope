"""Staged interview (ADR-0025): the declaration is built in the order its parts depend on.
Each stage asks one bundle of questions, takes the owner's answers at once, and reports how
far the domain has come. The current stage is the first one that is not done, so a later
change that breaks an earlier stage sends the interview back to it.

  sources → purpose → cast (roles, objects, links) → actions → transitions → invariants and rules
          → world (fixtures, scenarios) → handoffs → review (confirmations, glossary)

Within a stage, conflicts come first, then the questions for what is missing. In
transitions, ADR-0014's defaults, grouped rows, priorities and stop rule still apply.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..decl import Domain
from ..decl.words import a_ as _a

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
    Stage("invariants", "Invariants and rules", "What must always be true, however things got there; "
          "and what only some may bring about, whatever the action (ADR-0048).",
          ("invariants", "rules"), optional=True),
    Stage("world", "World and scenarios", "Realistic examples of everything, and flows that test "
          "the world, including a refused step.", ("world", "scenarios")),
    Stage("handoffs", "Handoffs", "What this domain hands to another domain, when, and with what.",
          ("handoffs",), optional=True),
    Stage("review", "Review", "Confirm what is right, and define the words a newcomer would misread.",
          ("glossary",)),
)
BY_NAME = {s.name: s for s in STAGES}
BUDGET = "the time budget is spent"
# Questions the owner may answer with "nothing here": once answered so, they are not asked again.
DECLINABLE = {"guard", "limit", "rule", "rest", "role", "object", "relate"}
# Questions asked once: whatever the answer, a later draft does not bring them back (#242's review).
ONCE = {"guard", "limit", "rule"}


def _qid(kind: str, subject: str) -> str:
    return hashlib.sha1(f"{kind}:{subject}".encode()).hexdigest()[:10]


# The invariants stage asks one question, for every thing at once, with "none" recommended (1c).
INVARIANTS_Q = _qid("invariants", "all")


class Plan:
    """The stage state of one draft. Built fresh for each call; it holds no state of its own."""

    def __init__(self, ws: Workspace, doc: dict[str, Any], d: Domain | None,
                 issues: list[Any], attempts: dict[str, int]):
        self.ws, self.doc, self.d, self.issues, self.attempts = ws, doc, d, issues, attempts
        log = ws._read(ws.log_path)
        self.skipped = {e["stage"]: e.get("reason") for e in log if e.get("kind") == "skip"}
        # A question answered with nothing to apply ("no limit", "no outcome rule") is not asked again.
        self.declined = {e.get("question_id") for e in log if e.get("kind") == "answer" and not e.get("decisions")
                         and not e.get("named") and not e.get("examples")}
        self.answered = {e.get("question_id") for e in log if e.get("kind") == "answer"}
        self.named, self.named_role = ws._named(log)
        self._ps: list[Any] | None = None

    @property
    def ps(self) -> list[Any]:
        """The passages a recommendation may cite (read once per plan)."""
        if self._ps is None:
            from .ruling import passages
            self._ps = passages(self.ws)
        return self._ps

    def pending(self) -> dict[str, dict[str, Any]]:
        """Actions the owner named whose actor is still open (ADR-0053: decided by a choice)."""
        d = self.d
        return {n: v for n, v in self.named.items() if d is None or n not in d.actions}

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
            return bool(d.actions) and not self.pending() and not self.rule_questions()
        if n == "transitions":
            if self.untracked() or not d.transitions:
                return False
            st = self.ws._stop(d, self.attempts)
            if not st["stop"]:
                return False
            if st.get("why") != BUDGET and self.rest_question() is not None:
                return False                 # cells the stop rule skipped are still asked, as one choice
            return not self.outcome_questions()
        if n == "invariants":     # an invariant, or the one question answered (its "none" skips the stage);
            return bool(d.invariants) or INVARIANTS_Q in self.answered    # a rule does not: rules are asked in transitions
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
            if kind in DECLINABLE and qid in self.declined:
                return
            out.append(Question(qid, kind, text, decides, priority, choices, subject))

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
            if not d.actions and not self.named:
                q("actions", "all", "What does each role do, to which thing? For each action: what must be "
                  "true first, and what it changes.", ["actions"])
            used = {r if isinstance(r, str) else r.role for a in d.actions.values() for r in a.actor}
            used |= set(self.named_role.values())
            settled = bool(d.actions) and not self.pending()    # after the actors are chosen
            for role in d.roles:
                if settled and role not in used:
                    q("actions", f"role:{role}", f"What does the {role} do here, if anything?", ["actions"])
            touched = {a.target for a in d.actions.values()} | {a.creates for a in d.actions.values()}
            touched |= {v.get("target") or v.get("creates") for v in self.named.values()}
            referenced = {l.to for l in d.links.values()}
            for obj in d.objects:
                if settled and obj not in touched and obj not in referenced:
                    q("actions", f"object:{obj}", f"How does a {obj} come to exist, and what changes it?",
                      ["actions"])
            out += self.actor_questions() + self.rule_questions()
        elif n == "transitions":
            for obj in self.untracked():
                q("transitions", f"stages:{obj}", f"What stages does a {obj} go through? Where does it "
                  "start, and which stages are final?", [f"transitions.{obj}"], 1e5)
            out += self.ws._cell_questions(d, self.attempts)
            rest = self.rest_question()
            if rest is not None and self.ws._stop(d, self.attempts)["stop"]:
                out.append(rest)
            out += self.outcome_questions()
        elif n == "invariants" and INVARIANTS_Q not in self.answered and n not in self.skipped:   # asked once
            from . import Choice, Question, choice_id
            things = ", ".join(sorted(d.transitions) or sorted(d.objects))
            out.append(Question(INVARIANTS_Q, "invariants", "Must anything always be true, in every stage and "
                                f"however it got there ({things})? Say what and why; or none.", ["invariants"], 0,
                                [Choice(choice_id(INVARIANTS_Q, 1, [], "invariants"), "none: skip the invariants stage",
                                        [], True, "the stages, each action's rules and the outcome rules already "
                                        "hold what was decided; an invariant is for a fact no action may break", "invariants")],
                                "all"))
        elif n == "world":
            if not d.world.fixtures:
                q("world", "fixtures", "Give realistic examples: at least one of each thing, with its key "
                  "facts. If you can, one in each stage.", ["world.fixtures"], 2)
            if not d.world.actors:
                q("world", "actors", "Who are typical people for each role? Names are enough.", ["world.actors"], 1)
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

    # -- choices where the rules are decided (ADR-0053 §2) ------------------------------------
    def _question(self, kind: str, subject: str, text: str, decides: list[str], priority: float,
                  choices: list[tuple[str, list[dict[str, Any]], bool, str]]) -> Question | None:
        from . import Choice, Question, choice_id
        qid = _qid(kind, subject)
        if (kind in DECLINABLE and qid in self.declined) or (kind in ONCE and qid in self.answered):
            return None
        return Question(qid, kind, text, decides, priority,
                        [Choice(choice_id(qid, i, dec), label, dec, rec, why if rec else "")
                         for i, (label, dec, rec, why) in enumerate(choices, 1)], subject)

    def actor_questions(self) -> list[Question]:
        """Who may take each action the owner named: one choice per role, the recommended one
        from the owner's words (the glossary's description of a role, the action's description,
        or the role question it was named under)."""
        from ..decl.words import term
        from .ruling import recommend_actor
        d, out = self.d, []
        for n, info in self.pending().items():
            obj = info.get("target") or info.get("creates") or "thing"
            desc = (info.get("description") or n).rstrip(".")
            top, why = recommend_actor(d, n, info, self.named_role.get(n))
            base = {k: info[k] for k in ("description", "target", "creates", "params") if k in info}
            choices = [(f"the {term(d, r)}", [{"path": f"actions.{n}", "value": {**base, "actor": [r]}}],
                        top == [r], why) for r in d.roles]
            if len(top) > 1:
                choices.insert(0, ("any of: " + ", ".join(term(d, r) for r in top),
                                   [{"path": f"actions.{n}", "value": {**base, "actor": top}}], True, why))
            q = self._question("actor", n, f"Who may {desc[:1].lower() + desc[1:]}? (the action {n}, on "
                               f"{'a new ' + obj if info.get('creates') else _a(obj)})", [f"actions.{n}"], 3, choices)
            if q is not None:
                out.append(q)
        return out

    def _drafted(self, a: Any) -> bool:
        st = getattr(a, "status", None)
        return getattr(st, "value", st) == "proposed"

    def rule_questions(self) -> list[Question]:
        """For each action the interview drafted that lets a thing go ahead (approve, pay, grant):
        who must not take it (only a person; not whoever made the thing), asked once; and a limit
        on a number where the owner's words state one, or else one question whose default is no
        limit (#242's review: a cap nobody stated is not recommended)."""
        from ..decl.words import term
        from .ruling import (HUMAN_CUES, OWN_CUES, about, allowing, creator, example_value, fmt, mentions,
                             thresholds, verbs)
        d, out = self.d, []
        if d is None:
            return out
        for n, a in d.actions.items():
            if a.target is None or not self._drafted(a) or not allowing(n, a):
                continue
            obj = a.target
            desc = a.description.rstrip(".")
            desc = desc[:1].lower() + desc[1:]
            said = about(self.ps, verbs(n, a))
            # who must not
            need_human = a.requires != "human"
            cr = None if any("actor.principal.id" in p.check for p in a.preconditions) else creator(d, obj)
            if need_human or cr is not None:
                human = [{"path": f"actions.{n}.requires", "value": "human"}]
                own = self.own_decisions(n, a, cr) if cr is not None else []
                hp = next((p for p in said if mentions(p, HUMAN_CUES)), None) if need_human else None
                op = next((p for p in said if mentions(p, OWN_CUES)), None) if own else None
                quote = "; ".join(f"your words say “{p.text}” ({p.ref})" for p in (hp, op) if p is not None)
                choices = []
                if need_human and own:
                    choices.append((f"only a person, and not whoever made the {term(d, obj)}", human + own,
                                    bool(hp and op), quote))
                if need_human:
                    choices.append(("only a person, never an agent on its own", human, bool(hp and not op), quote))
                if own:
                    choices.append((f"not whoever made the {term(d, obj)}, nor their agent", own,
                                    bool(op and not hp), quote))
                choices.append(("anyone with the role, agents too", [], not (hp or op),
                                f"nothing in your sources or answers limits who may {desc} beyond the role"))
                q = self._question("guard", n, f"Who must not {desc}, even with the role? (the action {n})",
                                   [f"actions.{n}"], 2, choices)
                if q is not None:
                    out.append(q)
            # a limit on a number
            every = [p for p, spec in d.objects[obj].properties.items() if spec.type in ("number", "integer")]
            numeric = [p for p in every if not any(f"target.{p}" in x.check for x in a.preconditions)]
            # a limit already set, or one the owner's words state, is the limit: no question on the others
            stated = len(numeric) < len(every)
            for prop in numeric:
                found = thresholds(d, obj, prop, self.ps, n)
                if not found:
                    continue
                stated = True
                pt = term(d, prop)
                choices, picked = [], False
                for v, why, passage, named_roles in found:
                    for r in d.roles:
                        rec = not picked and named_roles[:1] == [r]
                        picked |= rec
                        choices.append((f"over {fmt(v)} {pt}, only the {term(d, r)} may {desc}",
                                        self.limit_decisions(n, prop, v, r), rec, why))
                    rec = not picked and not named_roles
                    picked |= rec
                    choices.append((f"over {fmt(v)} {pt}, nobody may {desc}", self.limit_decisions(n, prop, v, None),
                                    rec, why))
                choices.append((f"no limit on {pt}", [], False, ""))
                q = self._question("limit", f"{n}.{prop}", f"Your words state a limit on {pt}. Over it, who may still "
                                   f"{desc}? (the action {n}; or type `over N` or `over N, only ROLE`)",
                                   [f"actions.{n}.preconditions"], 2, choices)
                if q is not None:
                    out.append(q)
            if numeric and not stated:
                choices = [("no limit (the default)", [], True,
                            "no passage or answer states a limit on " + ", ".join(term(d, p) for p in numeric))]
                for prop in numeric:
                    ex = example_value(d, obj, prop)
                    if ex is not None:
                        choices.append((f"over {fmt(ex[0])} {term(d, prop)} (like {ex[1]}), nobody may {desc}",
                                        self.limit_decisions(n, prop, ex[0], None), False, ""))
                q = self._question("limit", n, f"Is there a limit on {', '.join(term(d, p) for p in numeric)} before "
                                   f"someone may {desc}? No limit is the default. (the action {n}; type `over N`, "
                                   "`over N, only ROLE`, or `<fact> over N, only ROLE`)",
                                   [f"actions.{n}.preconditions"], 2, choices)
                if q is not None:
                    out.append(q)
        return out

    def own_decisions(self, n: str, a: Any, cr: tuple[str, str | None, list[tuple[str, int, str]]]) -> list[dict[str, Any]]:
        """"Not whoever made it": fail closed when who made it is not recorded, and compare the
        person with the person (`actor.principal.id` on both sides)."""
        from ..decl.words import term
        d, obj = self.d, a.target
        desc = a.description.rstrip(".")
        desc = desc[:1].lower() + desc[1:]
        prop, maker, align = cr
        own: list[dict[str, Any]] = []
        actions = self.doc.get("actions") or {}
        if maker is not None:
            if prop not in d.objects[obj].properties:
                own.append({"path": f"objects.{obj}.properties.{prop}", "value": {"type": "string", "optional": True}})
            effects = list((actions.get(maker) or {}).get("effects") or [])
            own.append({"path": f"actions.{maker}.effects",
                        "value": effects + [{"set": {f"new.{prop}": "actor.principal.id"}}]})
        for act in sorted({x for x, _, _ in align}):
            effects = [dict(e) for e in (actions.get(act) or {}).get("effects") or []]
            for x, i, key in align:
                if x == act:
                    effects[i] = {**effects[i], "set": {**effects[i]["set"], key: "actor.principal.id"}}
            own.append({"path": f"actions.{act}.effects", "value": effects})
        own.append({"path": f"actions.{n}.preconditions.not-the-creator", "value": {
            "check": f"exists(target.{prop}) and target.{prop} != actor.principal.id",
            "reason": f"Whoever made the {term(d, obj)}, or had their agent make it, cannot {desc}; and while who "
                      f"made it is not recorded, nobody can."}})
        return own

    def limit_decisions(self, n: str, prop: str, v: float, role: str | None) -> list[dict[str, Any]]:
        """A limit on a number before an action: over `v`, only `role` may take it (added to who may,
        if need be), or nobody may."""
        from ..decl.words import term
        from .ruling import fmt
        d = self.d
        a = d.actions[n]
        desc = a.description.rstrip(".")
        desc = desc[:1].lower() + desc[1:]
        pt = term(d, prop)
        if role is None:
            return [{"path": f"actions.{n}.preconditions.limit-{prop}", "value": {
                "check": f"target.{prop} <= {fmt(v)}", "reason": f"Over {fmt(v)} {pt}, nobody may {desc}."}}]
        out = [{"path": f"actions.{n}.preconditions.limit-{prop}", "value": {
            "check": f"target.{prop} <= {fmt(v)} or '{role}' in actor.roles",
            "reason": f"Over {fmt(v)} {pt}, only the {term(d, role)} may {desc}."}}]
        actor = list(((self.doc.get("actions") or {}).get(n) or {}).get("actor") or [])
        if role not in {r if isinstance(r, str) else r.get("role") for r in actor}:
            out.append({"path": f"actions.{n}.actor", "value": actor + [role]})
        return out

    def undecided(self) -> list[str]:
        d = self.d
        out = []
        for obj, tr in d.transitions.items():
            for name, a in d.actions.items():
                if a.target == obj and a.creates is None:
                    out += [f"transitions.{obj}.matrix.{s}.{name}" for s in tr.matrix
                            if tr.matrix[s].get(name, "undecided") == "undecided"]
        return out

    def rest_question(self) -> Question | None:
        """The cells ADR-0014's stop rule leaves undecided: each answer would be enforced (an
        undecided cell refuses), so they are asked, all at once, as one choice."""
        from . import _recommend
        cells = self.undecided()
        if not cells:
            return None
        d = self.d
        recs = []
        for p_ in cells:
            _, obj, _, state, action = p_.split(".")
            recs.append((p_, *_recommend(d.transitions[obj], state, action, obj)))
        choices = [
            ("each as recommended: " + "; ".join(f"{p_.split('.', 3)[3]}: {label}" for p_, _, label, _ in recs),
             [{"path": p_, "value": v} for p_, v, _, _ in recs], True,
             "; ".join(f"{p_.split('.', 3)[3]}: {why}" for p_, _, _, why in recs)),
            ("refuse them all, each with a reason",
             [{"path": p_, "value": {"deny": f"Not while {_a(p_.split('.')[1])} is {p_.split('.')[3]}."}}
              for p_ in cells], False, ""),
            ("leave them undecided: each is refused until decided, and listed in every change report", [], False, ""),
        ]
        return self._question("rest", ",".join(sorted(cells)), f"{len(cells)} cell(s) are still open, and nothing "
                              "has tried them yet: " + ", ".join(p_.split(".", 3)[3] for p_ in cells) +
                              ". Settle them at once?", cells, -1, choices)

    def outcome_questions(self) -> list[Question]:
        """Outcome rules (ADR-0048): which stage of a thing needs a person, or a role, whatever
        action reaches it. Asked for each thing with stages and no outcome rule yet, once its cells
        are settled: in every domain, drafted here or not (1c). It lives in transitions, so skipping
        the invariants stage never drops it."""
        import re

        from ..decl.words import term
        from . import _target
        from .ruling import HUMAN_CUES, about, mentions, stem, verbs
        d, out = self.d, []
        if d is None:
            return out
        for obj, tr in d.transitions.items():
            acts = {n: a for n, a in d.actions.items() if a.target == obj and a.creates is None}
            if any(r.on.startswith(f"{obj}.") for r in d.rules.values()):
                continue
            if any(tr.matrix[s].get(n, "undecided") == "undecided" for s in tr.matrix for n in acts):
                continue
            reached: dict[str, list[str]] = {}
            for s, row in tr.matrix.items():
                for n in acts:
                    t = _target(row.get(n))
                    if t is not None and t != s:
                        reached.setdefault(t, [])
                        if n not in reached[t]:
                            reached[t].append(n)
            if not reached:
                continue
            ot = term(d, obj)
            choices, picked = [], False
            for s, by in reached.items():
                rid = re.sub(r"[^A-Za-z0-9_-]", "-", s)
                said = about(self.ps, {stem(s)} | set().union(*(verbs(n, d.actions[n]) for n in by)))
                hp = next((p for p in said if mentions(p, HUMAN_CUES)), None)
                rec = hp is not None and not picked
                picked |= rec
                choices.append((f"only a person may bring {_a(ot)} to {s}", [{"path": f"rules.{obj}-{rid}-needs-a-person", "value": {
                    "on": f"{obj}.{s}", "requires": "human", "reason": f"Only a person brings {_a(ot)} to {s}."}}],
                    rec, f"your words say “{hp.text}” ({hp.ref})" if hp else ""))
                roles = sorted({r if isinstance(r, str) else r.role for n in by for r in d.actions[n].actor})
                for r in roles:
                    choices.append((f"only the {term(d, r)} may bring {_a(ot)} to {s}", [{
                        "path": f"rules.{obj}-{rid}-needs-{r}", "value": {
                            "on": f"{obj}.{s}", "requires": {"roles": [r]},
                            "reason": f"Only the {term(d, r)} brings {_a(ot)} to {s}."}}], False, ""))
            choices.append(("no outcome rule", [], not picked,
                            f"nothing in your sources or answers says who must bring {_a(ot)} to a stage; each "
                            "action's own rules still apply"))
            q = self._question("rule", obj, f"Whatever action gets {_a(ot)} there, does any stage need a person, or "
                               "one role, to bring it about? (An outcome rule holds for actions added later too.)",
                               ["rules"], -0.5, choices)
            if q is not None:
                out.append(q)
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
            return {"invariants": len(d.invariants), "rules": len(d.rules)}
        if n == "world":
            return {"fixtures": len(d.world.fixtures), "scenarios": len(d.scenarios)}
        if n == "handoffs":
            return {"handoffs": len(d.handoffs)}
        if n == "review":
            return {"proposed": len(self.ws._proposed(self.doc)), "glossary": len(d.glossary)}
        return {}


__all__ = ["BY_NAME", "STAGES", "Plan", "Stage"]
