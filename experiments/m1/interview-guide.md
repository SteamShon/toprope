# M1 instruments: a guide for writing them

Link: ② model is right, ① iterate safely. Status: **draft by the assistant, at the
researcher's request (2026-11-04)**. It is a guide, not an instrument: it holds **no
questions, answers, probes, intents or key entries**. Those are written by the researcher
alone (AGENTS.md). The researcher may edit or discard this guide freely.

## Why the agent stays out of the content
Writing gold is itself domain authoring, so it belongs in the Authoring domain as a
workflow. M1 still needs a yardstick from outside the system it measures, the way a
self-compiling compiler is still checked against an external test suite:
- The M1 drafter is an agent of the same model family as the one building the kernel. If
  that agent sees held-out answers, they can leak into defaults, question generation or
  checks.
- If the agent picks the questions, the system under test picks its own exam.

So:
- **This guide is not a Phase A source.** It holds no answers, but it shows which areas
  the gold probes. The source readers never read `experiments/` (their default exclusion),
  so keep it there.
- **Held-out gold, `change-key.yaml` and its mix** are never shown to an agent. When an
  agent runs the validator for you, it uses `--sealed`.
- **The shown half of the gold, the probe suite and the change intents** may be written
  in a chat interview where the agent asks only the area-level prompts below. You write
  the text, in your own words, into the files yourself.
- **Later** (from M2, if the researcher decides so), gold could be written with the
  generated authoring tool, the real dogfood, once M1 gives a reason to trust that tool.

## Decisions to make first (still open in the scope doc)
1. **How the instruments split across the two domains.** Option A: about 30 gold per self
   domain, with the handoff questions counted inside them (the experiment doc's figure).
   Option B: about 30 in total, weighted toward Authoring (less of your time, weaker
   evidence for Delivery).
2. **Whether handoff-breaking changes are seeded.** For example, a change that removes or
   renames something Delivery's request accepts. Seeding them tests the compile-time
   contract (ADR-0022). Leaving them out keeps the key smaller.

## Gold scenarios (`gold-scenarios.yaml`)

### What a good question is
- It asks **one fact** about how the work runs, in domain language, and is answerable from
  the model's read surface (allowed actions, states, denials and reasons, who may act).
- **The domain's declaration expresses it.** Facts the Toprope kernel guarantees for every
  domain are not gold, because no model can get them wrong. Examples: a handoff is
  delivered once, the contract is checked at compile time, the deploy floor in code.
- A fact that spans the two domains (what the receiver gets when the sender approves) names
  the composition (`toprope-self`, listed under `compositions`) as its `domain`. It is graded
  against the composed model (ADR-0026).
- It names its `domain`. If the same fact is asked of both domains (often at the handoff),
  give the copies one shared `fact` key and the same `held_out`. The fact counts once in
  scoring. Each copy must be answerable from its own domain's declaration; drop a copy that
  is not.
- It has one gradable answer. Prefer `yes_no`, `outcome`, `state` and `actors`, and keep
  `free_text` (graded by a person, with a rubric) to about one in six.
- **Held-out questions avoid facts stated verbatim** in the ADRs, the scope doc or the
  roadmap: Phase A may read those (scope doc decision). Ask about consequences,
  combinations and edge cases that the documents imply but do not state.
- It does not name elements (object, action or field names), because those are Phase A
  outputs. Describe them the way the owner would.
- It is stable: if the answer depends on a choice you have not made yet, decide it now or
  drop the question.
- It is not one of the **example questions already printed** in
  `docs/experiments/M1-self-compile.md` (for instance "What happens to an element no source
  supports?"). Those are public: use them, if at all, in the shown half.

### Coverage areas (ask yourself; aim for a spread, not a quota)
For each domain, pick questions across these areas. The prompts are deliberately generic.

| Area | Prompt to yourself |
|---|---|
| Lifecycle | Pick a thing the domain tracks and one of its stages. What can still happen to it there, and what cannot? |
| Who may act | For one step, which kinds of people or agents may take it? Who explicitly may not? |
| Agents on behalf of people | What may an agent do alone, what needs the person it acts for, and what is never an agent's to do? |
| Refusals and reasons | When a step is refused, what reason would the owner expect to read? |
| Always-true rules | What must never be true at any moment, however you got there? |
| Edge and exception paths | What happens on the unhappy path: rejected, withdrawn, superseded, stale, expired? |
| Evidence and provenance | What has to be on record before something counts, and where it came from? |
| Unknowns | What happens to something nobody has decided yet? |
| Change over time | What happens to things already in progress when the rules change? |
| Handoff (cross-domain) | What does one domain need from the other, and what happens when it cannot get it? |

Suggested mix per domain: lifecycle and refusals about 40%, who-may-act and agents about
25%, always-true rules about 15%, edge paths, unknowns and change over time the rest.
Mark about half `held_out: true`. Spread the held-out half across areas instead of
holding out a whole area.

## Probe suite (`probe-suite.yaml`)
- A probe is a **task** an agent is given after a deploy, with a starting situation, the
  behaviors that **must** be observable, and those that **must not**.
- Use situations where a careless tool would go wrong: an agent asked to finish something
  only a person may finish, a request in a stage where it does not apply, or a step with a
  missing prerequisite.
- Observable means visible in the tool's outputs or the recorded history, not in intent.
- No overlap with the gold questions or the domains' own scenarios, and no reference to the
  change key.
- Size: the experiment doc sets no number. A suggestion: about 8 to 12 per domain.

## Change requests (`change-requests.yaml`) and the key (`change-key.yaml`)
- About 20 **intents**, in the order an owner would ask for them, written as the owner
  would say them, each with a rationale. They are shown to every arm.
- Do not let the wording give the key away. Avoid words like "conflict", "break" or
  "seeded"; the validator warns about these.
- The key holds about 6 conflicts, 4 breakages and 10 clean changes. Write it **alone** and
  never paste it into a chat. Include at least two problem types the checks were **not**
  designed for (`designed_for_checks: no`), so M1 does not only measure what was
  anticipated.
- Useful kinds of problems to seed: a request that contradicts an earlier confirmed rule;
  one that removes something a later scenario relies on; one that makes past recorded
  behavior impossible to replay; one that strands things mid-way; and, if decided above,
  one that breaks the handoff.

## Verdict rules (`verdict-rules.yaml`)
Start from `verdict-rules.template.yaml`, which already holds the assistant's draft
values. Review each threshold, edit it, and set `status: frozen` yourself.

## A plan for the sessions
1. **Session 1 (about 45 min, alone):** decide the two questions above; write the held-out
   half of the Authoring gold.
2. **Session 2 (about 45 min, alone):** the held-out half of the Delivery gold and the
   handoff questions.
3. **Session 3 (about 45 min, optionally with the agent):** the shown half, and the probe
   suite. The agent asks the area prompts above; you write the text.
4. **Session 4 (about 30 min, alone):** the change intents, then the key.
5. Validate, mark the files frozen, run `freeze`, and commit in your own commit:
   ```bash
   uv run --with pyyaml python experiments/tools/instruments.py validate experiments/m1/instruments
   uv run --with pyyaml python experiments/tools/instruments.py freeze experiments/m1/instruments
   ```
   Change-check work (M0a sub-PR 8) starts after this commit.
