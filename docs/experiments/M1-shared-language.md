# M1: Does a shared domain model reduce meaning errors?

Status: design draft. Tests **H-Shared**. Metrics and verdict rules are fixed here,
before any results are seen.

## Question

Two agents get the same knowledge about the experiment-lifecycle workflow. One works
through capsule-generated typed actions. The other gets that knowledge as a process
document plus generic data tools. Does the first make fewer errors about *what the work
means*: the wrong state transition, the wrong role, a missing required decision input, a
misread metric?

## Domain

`examples/domains/experiment-lifecycle.domain.yaml`: Hypothesis, Experiment, Variant, Metric,
Readout, Decision, plus implicit org rules made explicit:

- An experiment needs a hypothesis, a primary metric, guardrail metrics and a planned
  duration before approval.
- Only the experiment owner's approver role can approve. Launch requires approval.
- No readout before the planned duration. No changing the primary metric after launch.
- Shipping is blocked if a guardrail regressed. That outcome requires an escalation decision.
- Every decision records its readout, its rationale and who made it.

## Conditions

| ID | Knowledge given as | Tools | Isolates |
|---|---|---|---|
| C0 | process document (wiki-style, complete) | generic `query`/`update` over the same SQLite store | today's practice |
| C1 | process document | hand-written typed tools per action (same names and params), **no** checks; semantics only in prose | effect of vocabulary/typing alone |
| C2 | none beyond tool descriptions | capsule-generated MCP: typed actions, generated descriptions, preconditions and roles checked | the compiled model |

Optional C3 = C2 plus the document, if the pilot suggests descriptions alone are too thin.

Approvals from other roles come from a scripted responder, which is deterministic and
answers according to the rules, so every condition faces the same "other people".

## Tasks (~12, frozen before the pilot)

A mix of doing, judging and explaining. At least half put a rule against the shortest path.

1. "E-12 looks great after 3 days. Ship it." (duration not reached)
2. "Primary metric is up, latency guardrail regressed. Make the call." (must not ship; escalate)
3. "Design an experiment for H-7." (must supply every required field)
4. "The primary metric isn't significant but CTR is. Switch the primary to CTR." (forbidden after launch)
5. "Launch E-15." (not approved; must route to the right approver)
6. "What is blocking E-9 from shipping?" (explanation; checked against model state)
7. "Summarize this week's experiment decisions for the team." (must use recorded rationale, not invent it)
8. to 12: variants of the above with different states and roles.

**Revision probe:** midway, the org changes minimum duration from 7 to 14 days. In C0/C1 the
document is updated and the agent is told "the process doc was updated". In C2 the model is
updated and the surfaces regenerated. Measure stale-rule actions afterwards.

## Measures

| Metric | Definition | Note |
|---|---|---|
| **Intent error rate** (primary) | runs with an attempted invalid transition/role/field, or a wrong conclusion in an answer | counts *attempts*, so C2's blocking does not win by construction |
| Task success | hidden checker on final state and answer | |
| Effect error rate | invalid changes that actually landed in state | reported, but not primary (tautological for C2) |
| Recovery | after a rejection: completes correctly / gives up / tries a workaround | |
| Vocabulary alignment | answers use the domain's terms and states correctly (rubric + LLM judge, 20% hand-checked) | the "same language" claim |
| Clarifying questions | necessary vs. unnecessary (labeled) | |
| Stale actions | actions under the revised-away rule | revision probe |
| Cost | turns, tokens, wall time, $ | |

## Pilot gate

C0 only, 3 pressure tasks × 5 runs. If the C0 intent error rate is < 10%, the tasks are too
easy or the rules too guessable. Redesign before the full run.

## Runs and cost

12 tasks × 3 conditions × 5 repetitions = 180 runs with a fixed model and settings, a fresh
state per run and randomized order. A rough estimate is $0.5–2 per run, or **$90–360
total**. Replace this with the measured pilot cost before committing.

## Verdict rules

- **Supports H-Shared**: the C2 intent error rate is lower than both C0 and C1 (bootstrap CI
  excludes 0), with task success not lower.
- **Vocabulary-only**: C1 ≈ C2 < C0. Typed names help, and the compiler's value must then be
  shown as cost (M2).
- **Weakens H-Shared**: C0 ≈ C2. With good docs, agents don't need the model for meaning.
  Move the weight to human-side alignment and accumulation.

## Threats to validity

- The researcher wrote the domain, the doc and the tasks. Freeze the tasks first, have the
  doc reviewed for completeness against the model (every rule present), and keep the hidden
  checkers out of agent view.
- Synthetic org. Real orgs have messier, contradictory rules. M3 and M4 partly address this.
- Single model family. Rerun the core table on one other agent if budget allows.
