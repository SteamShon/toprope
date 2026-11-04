# M1: Self-compile, and safe iteration vs. natural-language skills

Link: ① iterate safely, ② model is right. Status: design draft. Metrics and verdict rules
are fixed here, before any results are seen.

## Why this design

The premise is that nobody defines a domain correctly in one go (P0). So the decisive
question is not how good the first draft is. It is whether a domain can be **changed many
times, cheaply and safely**. That is the compiler's core job: compare each change with the
existing declaration, report breakage and conflicts before deployment, and give a preview
to try the change.

The natural rival is the natural-language skill (SKILL.md, AGENTS.md). Its changes cannot be
checked against the existing text before deployment. M1 compares the two directly.

Toprope's own authoring workflow is the domain (self-compile). It is a hidden workflow the
researcher knows well, and the authoring tool generated from it is used in every later
milestone.

## Domain in scope

Toprope's authoring workflow, roughly: source → draft element → interview question →
confirmation (human) → domain version → compile and change check → preview → deploy →
event log → proposal → decision (human). The actual objects and actions are an output of
the experiment and are not written in advance.

## Phase A: Build by iterating (① ②)

The domain is built through the raw-material pipeline, and every step is a compiled
iteration:

| Stage | Raw material | Who works |
|---|---|---|
| S1 System | the M0 kernel code and schema | agent drafts |
| S2 Records | this repository's docs, ADRs, notes, and session transcripts | agent enriches, quoting sources |
| S3 Interview | the researcher as domain owner | agent asks, human answers |
| S4 Use | the generated authoring tool, used on one small change | human and agent |

Every element carries `source` and `status`. Agents write only `proposed`; only the human
confirms. The authoring tool used in S4 and handed to M2 is generated from the model.

Recorded per iteration: held-out scenario accuracy, human minutes, edits, and unsupported
rules. This gives an **accuracy-over-iterations curve**, which is the evidence for ② and
the sanity check for P0 (was the first draft already right?).

## Phase B: Change sequence, Toprope vs. natural-language skill (①)

### Arms (equal information)

- **NL arm.** The confirmed Phase A model is rendered by hand into a natural-language skill
  (SKILL.md plus examples) that contains the same rules. Each change is applied as a text
  edit. Pre-deploy check: an LLM is asked to review the edit against the whole skill for
  conflicts and breakage. This is the strongest fair baseline.
- **Toprope arm.** The same change is applied to the declaration. Pre-deploy check: the
  compiler's change checks plus a preview build.

### Change requests (frozen before Phase A, researcher-written)

About 20 realistic change requests to the self domain, in a fixed order. The researcher
**seeds** known problems and keeps the answer key hidden from both arms:
- about 6 that conflict with an earlier rule
- about 4 that break an existing reference, scenario or past behavior
- about 10 that are clean.

Examples:
- "Require a second confirmer for permission-related elements."
- "Let agents confirm typo fixes." (conflicts with no self-approval)
- "Rename `unknown` to `open`." (breaks references and past logs)

### "Deploy" and post-deploy discovery

After each change, both arms run the scenario suite with an agent. For the NL arm, the
agent works from the skill. For the Toprope arm, it works through the generated MCP.
A seeded problem that was not flagged before deploy, but shows up as a scenario failure or
wrong behavior, counts as **found after deploy**. One that never shows up counts as
**silent**.

## Gold standard (frozen before Phase A)

- About 30 scenario questions about the authoring workflow, half held out. Examples:
  - "Can an agent confirm its own drafted precondition?"
  - "What happens to an element no source supports?"
  - "When does a representation-only change rebuild MCP?"
- The change-request list and its seeded-problem key.
- Agents never create or edit either one (AGENTS.md).

## Measures

| Metric | Definition | Link |
|---|---|---|
| **Pre-deploy recall** (primary) | seeded problems flagged before deploy / all seeded problems | ① |
| **Pre-deploy precision** | flags that were real problems / all flags (false alarms matter: experts stop reading noisy checks) | ① |
| Found after deploy / silent | seeded problems missed before deploy, then surfaced / never surfaced | ① |
| **Iteration time** (primary) | edit → validated preview, wall time and human minutes, per change | ① |
| Check breakdown | which check caught what: structural, semantic, scenario regression, log replay, NL lint | ① |
| **Held-out accuracy** (primary) | after Phase A, and after Phase B | ② |
| Accuracy-over-iterations | Phase A curve; accuracy of the first draft | ② and the P0 sanity check |
| Unsupported rules | rules with no source and no confirmation | ② |
| Generated vs hand-built | share of the authoring tool that is generated; hand edits to generated code | self-compile |
| Cost | tokens, $, human minutes per stage and per change | all |

## Verdict rules

- **Supports ①**:
  - Toprope pre-deploy recall ≥ 80% with precision ≥ 70%
  - the NL arm's recall at least 30 points lower
  - median iteration time ≤ 5 minutes to a validated preview, with no hand edits to
    generated surfaces.
- **Weakens ①**: the NL arm with LLM review comes within 15 points of Toprope's recall, or
  Toprope's precision < 50%, or most seeded breakages are found only after deploy in both
  arms.
- **Supports ② (self)**: held-out accuracy ≥ 80%, unsupported rules ≤ 10%, total human time
  ≤ 4 h for Phase A.
- **Self-compile claim** holds only if the tool used in S4 and handed to M2 is generated
  from the model, with hand edits listed.

## Risks

- **Seeding bias.** The researcher writes both the checks and the seeded problems. Freeze
  the change list before building the checks. Include problem types the checks were not
  designed for, and report per-type recall.
- **Unequal information.** The NL skill is written from the same confirmed model. A second
  reader checks that every rule appears in both.
- **Circularity and self-approval.** The gold set, the change key and the verdict checks
  live outside the model and are never edited by the loop. "No agent can confirm" is itself
  a scenario.
- **Designer bias.** The self domain favors success. M2 repeats Phase B on a dogfood
  domain, and only M2 counts as evidence outside the self domain.
