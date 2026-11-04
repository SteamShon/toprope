# ADR-0025: A staged authoring interview: one bundle per stage, with progress

- Link: ① iterate safely, ② model is right · Status: **proposed** (drafted by the assistant
  from the researcher's design, 2026-11-04; the researcher accepts or amends) · 2026-11-04
- Amends: ADR-0014 (question order). Defaults, grouped cells, priorities, the stop rule,
  "answers are elements" and privacy are kept.

## Context
ADR-0014 orders interview questions in one priority list: purpose, conflicts, defaults,
grouped rows, confirmations. In practice an owner thinks about a domain in the order its
parts depend on. You cannot say what an action does before you know who takes part and what
is tracked. You cannot fill a matrix before the actions exist. One question at a time is
also slow: the owner answers better when a related set of questions is asked together, and
they want to see how far the domain has come.

## Decision
1. **Stages, in dependency order.** The declaration is built in nine stages:

   | Stage | Fills | Done when |
   |---|---|---|
   | sources | where the raw material is: paths or links | some source has content |
   | purpose | problem, success metric, announcement | all three are written |
   | cast | roles, objects (with key facts), links | roles and objects exist, no conflicts |
   | actions | who does what to which thing, preconditions, effects | actions exist, no conflicts |
   | transitions | the stages of each tracked thing, and the matrix | every acted-on object has stages, no conflicts, ADR-0014's stop rule holds |
   | invariants | what must always hold | invariants exist, or the owner says there are none |
   | world | fixtures, actors, scenarios | fixtures and scenarios exist, no conflicts |
   | handoffs | what goes to another domain | handoffs exist, or the owner says there are none |
   | review | confirmations, glossary | every earlier stage is done and nothing is left unconfirmed |

   The **current stage** is the first one that is not done. If a later change breaks an
   earlier stage (a conflict in its part of the declaration), the interview goes back to it.
2. **One bundle per stage.** For the current stage, the drafter first proposes what the
   sources support, citing them. Then it asks the stage's **bundle**:
   - the conflicts in that stage first
   - then questions for what is missing. Examples: who takes part; an undescribed or
     unrelated object; a role that does nothing; an acted-on object with no stages.
   - in the transitions stage, ADR-0014's defaults and grouped rows, by priority.

   The owner answers the whole bundle at once. The answer is recorded in their words
   against the bundle id, and its decisions become proposed elements citing it.
3. **Progress is shown at every step.** Each stage is reported as done, current, todo or
   skipped, with counts: roles, objects, links, actions, cells and undecided cells,
   invariants, fixtures, scenarios, handoffs, and unconfirmed elements.
4. **Optional stages are skipped in the owner's words.** Invariants and handoffs may
   legitimately be empty. The owner says so, and the reason is logged. No other stage can be
   skipped.
5. **Sources may be links.** A link source is fetched once into a snapshot inside the
   workspace (`.toprope/snapshots/<id>/`, http(s), text only, at most 2 MB). It is then read,
   chunked and redacted like a file, so refs stay stable. Local-only applies to links too. A
   private document behind a login is downloaded by the owner and given as a path.
6. **The glossary is collected throughout** and settled in review, because terms come up
   while describing people and things, not in a stage of their own.

## Consequences
- `questions()` returns the current stage's bundle with progress. `progress()` and
  `skip_stage()` are added to the workspace, the authoring MCP and `toprope-author`, as is
  `fetch` for link sources.
- M1 measures questions asked per stage and the minutes per stage, in addition to ADR-0014's
  measures.
- This ADR is public, so the stage order and what each stage asks are visible to Phase A.
  Gold questions about the authoring workflow that restate this ADR can only be in the shown
  half.
