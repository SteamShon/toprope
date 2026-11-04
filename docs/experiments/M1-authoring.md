# M1: Can an implicit workflow be turned into a usable domain, cheaply?

Status: design draft. Tests **H-Author** (claim ①, "can be built") and **H-Fidelity**
(claim ②, "the model is right"). Metrics and verdict rules are fixed here, before any
results are seen.

## Why this first

Toprope's claims form a chain (see the charter, §3). If a domain cannot be built cheaply,
nobody builds one, and shared language, evolution and organizational gains never start.
This is also where Toprope differs most from Foundry-style ontologies, which work but are
expensive enough that mainly large organizations build them.

## Question

Starting from what an organization already has, and using raw material in order of how
easily it can be automated, how much human time does it take to reach a domain model that
answers workflow questions correctly? What do later changes cost?

## Pipeline under test

| Stage | Raw material | Who works | Output |
|---|---|---|---|
| S1 System | existing code, DB schema, API of an experimentation system | agent drafts | draft model (objects, links, actions, preconditions) with source links |
| S2 Records | docs, issues, discussions, changelogs | agent enriches | rules found only in records, each with a quote |
| S3 Interview | the domain owner | agent asks, human answers | corrected and confirmed rules; unknowns resolved or marked |
| S4 Use | generated MCP + UI, scenario runs | human and agent use it; agent proposes fixes | fixes found only by using it |

Every model element carries **provenance** (system / record / interview / use) and a
**status** (proposed / confirmed / unknown). Agents never confirm their own proposals.

## Source system

Candidate: an open-source experimentation platform (e.g. GrowthBook), because it has code,
schema, docs and public issues about experiment workflow. Feasibility and license are
checked in M0. Fallback: a small synthetic company repo plus synthetic records written
*before* the gold set, by a separate prompt, so the gold set does not leak into it.

## Gold standard (built before any drafting)

- **Scenario set**, about 40 questions with answers, written by the researcher as domain
  owner from experiment-operations experience and the platform's docs. Examples:
  - "Can a running experiment's primary metric be changed?"
  - "Who must approve before launch?"
  - "What blocks E-9 from shipping?"
  - "What happens if a guardrail regresses?"
- Half are **held out** from S4 use, so S4 cannot overfit to them.
- Evaluation is behavioral: answers are derived from the model, using only its generated
  read surface, and checked against gold. This avoids rewarding one particular modeling
  style.
- `examples/domains/experiment-lifecycle.domain.yaml` is a schema illustration written
  before M1. It is **not** given to the drafting agent and is not the gold standard.

## Measures (after each stage)

| Metric | Definition |
|---|---|
| **Fidelity** (primary) | held-out scenario accuracy |
| **Human time** (primary) | minutes the human spends per stage (reviewing, answering, editing) |
| Human edits | count of human add/change/delete operations on the model |
| Unsupported rules | model rules with no source or confirmation (hallucinations); share of all rules |
| Unknowns flagged | rules marked unknown rather than guessed |
| Interview load | questions asked, answer time, unnecessary questions (labeled) |
| Agent cost | tokens and $ per stage |
| **Change cost** | after S4, apply 3 changes (e.g. minimum duration 14 days; extra approver for high-traffic experiments; a new guardrail). Per change: human minutes, edits, regressions on the scenario set, any hand edits to generated surfaces (target: zero) |

## Baseline

The researcher hand-authors one slice (the approval sub-workflow) from the same sources,
time-boxed, **before** seeing any agent output, and scores it on the slice's scenarios.
This gives a human-only cost/accuracy rate to compare against. With n=1 this is a sanity
anchor, not a statistical baseline.

## Pilot gate

Run S1 alone in M0. If the draft is unusable (held-out accuracy < 20% *and* most elements
unsupported), change the source system or the drafting approach before M1.

## Verdict rules

- **Supports H-Author / H-Fidelity**: held-out accuracy ≥ 80% after S3–S4, with total human
  time ≤ 4 hours, each later change ≤ 30 minutes with no hand edits to generated surfaces,
  and unsupported rules ≤ 10%.
- **Weakens**: human time is mostly spent correcting agent drafts (the per-scenario rate is
  worse than the hand-authored slice), or accuracy plateaus below 70%.
- Also report which stage contributed most. This tells us whether the
  system → records → interview → use order is right.

## Threats to validity

- n=1 domain owner who is also the researcher: gold set frozen first and hidden from the
  agent; the baseline slice done before seeing agent output.
- An OSS platform encodes its *product's* workflow, not one organization's oral rules.
  Records and interview stages are where org-specific rules enter; report them separately.
- Interview answers come from the researcher's experience at a prior employer: only general
  practice is used, nothing confidential.
