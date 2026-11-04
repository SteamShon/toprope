# ADR-0014: Interview design: defaults, grouped cells, priorities and a stop rule

- Link: ① iterate safely, ② model is right · Status: accepted · 2026-11-04 · decided by: SteamShon
- Origin: design review 2026-11-04 (docs/reviews/2026-11-04-design-review.md, finding 1)

## Context
The cost and accuracy of ① and ② are decided mostly by the interview. A matrix grows as
states × actions × roles. With 10 states, 15 actions and 4 roles there are 600 cells. Asking
about each cell would make ① fail on cost.

## Decision
1. **Defaults first.** The drafter proposes defaults that the owner confirms once, instead
   of cell by cell. Examples:
   - an action **applies only in** the states listed in its `applies_in` field (a field
     this ADR adds to actions), and is `n/a` elsewhere
   - a role may perform an action only where its actor list says so
   - terminal states allow no state-changing action.

   A default is an element like any other, with `source` and `status`. **Only a confirmed
   default** decides cells, and it never overrides a cell that is explicitly declared,
   including one explicitly declared `undecided`, or a cell that real attempts have hit.
   Those cells are still asked about. Change reports count cells decided by defaults
   separately from cells decided by explicit answers, so defaults cannot hide gaps.
2. **Group cells into one question** when they share an outcome. For example, *"Once an
   experiment has ended, can anything still change its status?"* settles a whole row.
3. **Prioritize** remaining questions by:
   - attempts recorded in the event store: cells that real users or agents actually hit
   - risk: irreversible effects or external side effects
   - how many cells the answer would decide.
4. **Stop rule.** The interview stops when every reachable cell that has been attempted, or
   that leads to an external effect, is decided, or when a time budget set by the owner is
   spent. Remaining `undecided` cells deny by default and stay listed (ADR-0010).
5. **Answers are elements.** Each answer becomes a cell decision, a default or an invariant
   with `source: interview`, the question text and the answer quote.
6. **Privacy.** Sources sent to an LLM (code, records, transcripts) pass a redaction step
   for secrets and personal data. The owner can mark a source local-only, so it is never
   sent to a hosted model. The drafter records which sources it used.

## Consequences
- M1 measures questions asked, cells decided per question, and the share of cells decided
  by defaults.
- Interview tools are exposed through the authoring MCP, so an external agent (e.g. Claude
  Code) can run the interview with no Toprope runtime of its own (ADR-0017).
