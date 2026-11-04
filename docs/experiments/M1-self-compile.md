# M1: Self-compile, and safe iteration vs. natural-language skills

Link: ① iterate safely, ② model is right. Status: design draft.

**Freeze status.** The metrics and verdict rules below are a **draft proposed by the
assistant**. The researcher reviews, edits and freezes them in their own commit, together
with the gold scenarios, the post-deploy probe suite and the change-request list. All of
this happens in M0, **before the change-check pipeline is built** (AGENTS.md). Until then,
nothing here is preregistered.

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
event store → proposal → decision (human). Optionally, the self domain also declares Toprope's own components (core, compilers,
server, shell, harness, event store) as object types with links, so the structure layer of
its world map can replace the README's component diagram (ADR-0020). The researcher decides
this when freezing the gold set, and adds gold questions for it if included. The actual
objects and actions are an output of
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
- **Structured-spec arm (ADR-0019).** The same change is applied to the same YAML
  declaration, but with **no compiler**. Pre-deploy check: the same LLM review as the NL arm.
  This separates the effect of having a structured spec from the effect of the compiler.
- **Toprope arm.** The same change is applied to the declaration. Pre-deploy check: the
  compiler's change checks plus a preview build.

### Change requests (researcher-written, frozen in M0 before the checks are built)

About 20 realistic change requests to the self domain, in a fixed order, written as
**intents** in domain language rather than element names, because the element names are
an output of Phase A. The researcher **seeds** known problems and keeps the answer key
hidden from every arm. The key is also written by intent: "conflicts with the
no-self-approval rule", or "breaks anything that refers to the not-yet-known state".
Mix:
- about 6 that conflict with an earlier rule
- about 4 that break an existing reference, scenario or past behavior
- about 10 that are clean.

Examples:
- "Require a second confirmer for permission-related elements."
- "Let agents confirm typo fixes." (conflicts with no self-approval)
- "Rename the not-yet-known element state to `open`." (breaks references and past logs)

**Binding step.** After Phase A, and before any arm runs, the researcher maps each
intent and key entry to concrete element names in the Phase A model, and freezes that
mapping in a commit. A request whose target does not exist in the model is recorded as
unbindable and excluded from recall, and the exclusion is reported.

### Three scenario sets, kept apart

| Set | Who sees it | Purpose |
|---|---|---|
| **Domain scenarios** | all three arms, before deploy. Toprope runs them as scenario regression. The NL skill and the structured spec include them as worked examples, and their LLM reviewers get them too. | the domain's own tests |
| **Post-deploy probe suite** | neither arm, before deploy | discovers problems after "deploy" |
| **Held-out gold** | neither arm, ever. Not fed to any iteration. | measures ② |

The probe suite and the held-out gold are written by the researcher and do not overlap
with the domain scenarios. So no arm's pre-deploy check is the same instrument as
post-deploy discovery.

### "Deploy" and post-deploy discovery

After each change, every arm runs the **post-deploy probe suite** with an agent, using the
same model and the same generic data tools over the same state:
- In the NL arm, the agent works from the skill text.
- In the structured-spec arm, it works from the YAML declaration, given as text.
- In the Toprope arm, it works through the generated MCP.
A seeded problem that was not flagged before deploy, but shows up in the probe suite,
counts as **found after deploy**. One that never shows up counts as **silent**.

## Gold standard (researcher-written, frozen in M0 before the checks are built)

- About 30 scenario questions about the authoring workflow, half held out. Examples:
  - "Can an agent confirm its own drafted precondition?"
  - "What happens to an element no source supports?"
  - "When does a representation-only change rebuild MCP?"
- The post-deploy probe suite (separate from the gold set and the domain scenarios).
- The change-request list and its seeded-problem key (by intent), and later the binding.
- Agents never create or edit any of these: gold scenarios, probe suite, change list, key or
  binding (AGENTS.md).

## Measures

| Metric | Definition | Link |
|---|---|---|
| **Pre-deploy recall** (primary) | seeded problems flagged before deploy / all seeded problems | ① |
| **Pre-deploy precision** | flags that were real problems / all flags (false alarms matter: experts stop reading noisy checks) | ① |
| Found after deploy / silent | seeded problems missed before deploy, then surfaced / never surfaced | ① |
| **Iteration time** (primary) | edit → validated preview, wall time and human minutes, per change; broken down into impact report, affected harness and preview (ADR-0013) | ① |
| Selection misses | tests that failed in the background full run but were passing from cache, i.e. impact-analysis bugs (target: 0) | ① |
| Check breakdown | which check caught what: structural, semantic, scenario regression, log replay, NL lint | ① |
| **Held-out accuracy** (primary) | after Phase A, and after Phase B | ② |
| Accuracy-over-iterations | Phase A curve; accuracy of the first draft | ② and the P0 sanity check |
| Unsupported rules | rules with no source and no confirmation | ② |
| Interview efficiency (ADR-0014) | questions asked; cells decided per question; share of cells decided by confirmed defaults | ① ② |
| Matrix completeness | share of (state, action) cells decided rather than `undecided`; cells decided through the interview vs. drafted from sources | ② |
| Harness findings | invariant violations and parity failures found before deploy, and by which part (cell tests, exploration, flows) | ① |
| Generated vs hand-built | share of the authoring tool that is generated; hand edits to generated code | self-compile |
| Cost | tokens, $, human minutes per stage and per change | all |

## Verdict rules

- **Supports ①** (compile-time checking) requires **all** of:
  - Toprope pre-deploy recall ≥ 80% with precision ≥ 70%
  - the NL arm's recall at least 30 points lower
  - the structured-spec arm's recall at least 10 points lower (the compiler's contribution)
  - median iteration time ≤ 5 minutes to a validated preview, with no hand edits to
    generated surfaces.
- **Weakens ①**: the NL arm with LLM review comes within 15 points of Toprope's recall, or
  Toprope's precision < 50%, or most seeded breakages are found only after deploy in both
  arms.
- **Narrowed ①**: Toprope beats NL by ≥ 30 points but beats the structured spec by < 10.
  The gain comes from writing the domain down in a structured form, not from the compiler.
  This is recorded as **weakened** for the compiler claim, takes precedence over "supports",
  and is reported with all three numbers.
- **Inconclusive ①**: any outcome not covered above. For example, a recall gap of 15–30
  points, or precision of 50–70%. It is reported as inconclusive with the numbers, and is
  not read as support. M2 repeats the comparison.
- **Supports ② (self)**: held-out accuracy ≥ 80%, unsupported rules ≤ 10%, total human time
  ≤ 4 h for Phase A, and accuracy rising over iterations (the final accuracy is higher than
  the first draft's).
- **Weakens ② (self)**: accuracy plateaus below 70%, or unsupported rules stay above 20%
  after S3.
- **Inconclusive ②**: anything in between.
- **P0 sanity check** (not a verdict): if the first draft already reaches ≥ 80% held-out
  accuracy, record that P0 did not show up on this domain.
- **Self-compile claim** holds only if the tool used in S4 and handed to M2 is generated
  from the model, with hand edits listed.

## Risks

- **Seeding bias.** The researcher writes both the checks and the seeded problems. The
  change list, the key, the gold set and the probe suite are frozen in M0, before the
  change-check pipeline is built. Include problem types the checks were not
  designed for, and report per-type recall.
- **Unequal information.** The NL skill and the structured spec are written from the same
  confirmed model. A second reader checks that every rule appears in all three arms.
- **Circularity and self-approval.** The gold set, the change key and the verdict checks
  live outside the model and are never edited by the loop. "No agent can confirm" is itself
  a scenario.
- **Designer bias.** The self domain favors success. M2 repeats Phase B on a dogfood
  domain, and only M2 counts as evidence outside the self domain.
