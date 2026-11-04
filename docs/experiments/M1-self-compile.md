# M1: Self-compile

Link: ① can be built, ② model is right. Status: design draft. Metrics and verdict rules
are fixed here, before any results are seen.

## Why Toprope itself first

Authoring a domain is itself a hidden workflow. Someone gathers sources, an agent drafts,
the owner is interviewed, elements are confirmed or left unknown, the model is compiled,
used, and changed. Modeling that workflow in Toprope does two things:

1. It tests ① and ② on a domain the researcher knows deeply and can judge.
2. It produces the authoring tool used for every later domain. The tool is generated from
   the model instead of hand-built. If this fails, the rest of the plan uses a hand-built
   tool, and the self-compile claim is dropped.

## Domain in scope

Toprope's authoring workflow, roughly:

```
Source ─► Draft element ─► Interview question ─► Confirmation (human)
                                   │                     │
                                   ▼                     ▼
                              Unknown            Domain version ─► Compile ─► Surfaces
                                                         ▲                       │
                               Decision (human) ◄─ Proposal ◄─ Event log ◄───────┘
```

Objects such as Source, Element, Question, Confirmation, DomainVersion, Proposal, Decision.
Actions such as draft, ask, confirm, mark-unknown, compile, propose, decide. The real list
is the experiment's output and is **not** written in advance.

## Pipeline (raw material in order of how easily it can be automated)

| Stage | Raw material for the self domain | Who works |
|---|---|---|
| S1 System | the M0 kernel code and schema | agent drafts |
| S2 Records | this repository's docs, ADRs, Korean notes, and the session transcripts where Toprope was defined | agent enriches, quoting sources |
| S3 Interview | the researcher as domain owner | agent asks, human answers |
| S4 Use | generate the authoring tool from the model, then use it to make one small change to the self domain | human and agent, agent proposes fixes |

Every element carries `source` and `status`. Agents can only write `proposed`. Only the
human confirms.

## Gold standard (frozen before S1)

- About 30 scenario questions about the authoring workflow, written by the researcher.
  Examples:
  - "Can an agent confirm its own drafted precondition?"
  - "What happens to an element no source supports?"
  - "When does a change regenerate the MCP?"
  - "Who decides a proposal mined from logs?"
- Half are held out from S4. Answers are derived from the model through its generated read
  surface and checked against gold.

## Measures (after each stage)

| Metric | Definition |
|---|---|
| **Fidelity** (primary) | held-out scenario accuracy |
| **Human time** (primary) | minutes per stage spent reviewing, answering and editing |
| Human edits | add, change and delete operations on the model |
| Unsupported rules | share of rules with no source and no confirmation |
| Unknowns flagged | rules marked unknown instead of guessed |
| Interview load | questions asked, answer time, unnecessary questions |
| Agent cost | tokens and $ per stage |
| Generated vs hand-built | share of the authoring tool's surface that is generated; any hand edits to generated code |
| **Change cost** | three changes to the self domain (e.g. require a second confirmer for permission-related elements; add a "deprecated" element status; require evidence on every proposal). Per change: human minutes, edits, scenario regressions, hand edits to generated surfaces (target: zero) |

## Verdict rules

- **Supports ① ② (self)**: held-out accuracy ≥ 80%, total human time ≤ 4 h, each change
  ≤ 30 min with no hand edits to generated surfaces, unsupported rules ≤ 10%.
- **Weakens**: human time is mostly spent correcting drafts, or accuracy plateaus below 70%.
- **Self-compile claim**: holds only if the tool used in S4 and handed to M2 is generated
  from the model, with hand edits listed.
- Also report which stage contributed most, as a check on the raw-material order.

## Self-compile risks

- **Circularity.** The system could change its own rules and its own tests together. The
  gold set and the verdict checks live outside the model and are never edited by the loop.
- **Self-approval.** No action in the model lets an agent confirm or decide. This is
  checked as a scenario in the gold set.
- **Designer bias.** The researcher designed both Toprope and this domain, so the self
  domain is easier than real ones. That is why M2 replicates on a dogfood domain, and only
  M2 counts as evidence outside the self domain.
- **Stopping.** Self-application stops at one generated tool version for M1. Further
  self-improvement waits for M4.
