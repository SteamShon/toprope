# M1: Self-compile, and safe iteration vs. natural-language skills

Link: self-compile feasibility; ① iterate safely and ⑥ (the handoff) as a **pilot**. M1 gives
no link verdict: ② (ADR-0030) and ① (ADR-0034) are judged in M2. Status: design draft.

**Freeze status.** The researcher freezes the probe suite and the verdict rules before the
change-check pipeline is built, and the change-request list and its key before the pilot
runs (ADR-0034). Because these are self-domain instruments and feed no link verdict, an
agent may draft them at the researcher's request, including multiple-choice options; the
researcher selects and freezes them (AGENTS.md). No gold set in M1 (ADR-0031).

## Why this design

The premise is that nobody defines a domain correctly in one go (P0). So the decisive
question is not how good the first draft is. It is whether a domain can be **changed many
times, cheaply and safely**. That is the compiler's core job: compare each change with the
existing declaration, report breakage and conflicts before deployment, and give a preview
to try the change.

The natural rival is the natural-language skill (SKILL.md, AGENTS.md). Its changes cannot be
checked against the existing text before deployment. M1 compares the two directly.

Toprope's own workflows are the domains (self-compile, ADR-0022). There are two:
**Domain Authoring** and **Domain Delivery**, joined by a typed handoff. They are hidden
workflows the researcher knows well, and the tools generated from them are used in every
later milestone. Scope: [`M1-self-domains-scope.md`](M1-self-domains-scope.md).

## Domains in scope

- **Domain Authoring**, roughly: source → draft element → interview question → confirmation
  (human) → domain version → change report → approval → proposal → decision (human).
- **Domain Delivery**, roughly: delivery request → build → harness run → preview → deploy
  approval (human) → deploy → activate → verify → rollback.
- **Handoff**: an approved domain version becomes a delivery request through Delivery's
  published interface.

Boundaries and candidate vocabulary: [`M1-self-domains-scope.md`](M1-self-domains-scope.md). Optionally, the self domain also declares Toprope's own components (core, compilers,
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
| S2 Records | this repository's docs, ADRs, notes, the scope document and session transcripts (allowed, scope decisions) | agent enriches, quoting sources |
| S3 Interview | the researcher as domain owner | agent asks, human answers |
| S4 Use | the generated authoring and delivery tools, used on one small change | human and agent |

Every element carries `source` and `status`. Agents write only `proposed`; only the human
confirms. The authoring tool used in S4 and handed to M2 is generated from the model.

Recorded per iteration: held-out scenario accuracy, human minutes, edits, and unsupported
rules. This gives an **accuracy-over-iterations curve**, which is the evidence for ② and
the sanity check for P0 (was the first draft already right?).

## Phase B: Change sequence, Toprope vs. natural-language skill (①)

How it runs (who plays each role, where, the stand-in for person-only steps, and when the
key is opened): [ADR-0040](../adr/0040-m1-phase-b-execution-protocol.md).

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

All three arms carry **both domains and the handoff contract**. The NL skill describes
Delivery's request interface in prose, and the structured spec includes the `handoffs`
declaration. Whether handoff-breaking changes are part of the seeded mix is the researcher's
call when freezing the change list. If they are, recall is reported with and without them,
because only the Toprope arm has a compiled interface to break.

### Change requests (the researcher's, agent help allowed; frozen before the pilot runs)

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

Templates, the freeze procedure and the `verify` check:
[`experiments/m1/`](../../experiments/m1/README.md).

- About 30 scenario questions per self domain (Authoring, Delivery, and the handoff between them), half held out
  in each domain. Each item names the domain whose compiled model answers it, or the
  composition (ADR-0026) for a fact that spans both domains, graded against the composed model. The same fact
  asked of both domains shares a `fact` key: its copies share `held_out`, and it counts once in
  scoring (each copy weighs 1/n; verdict rules `scoring.unit: fact`). Facts that the Toprope
  kernel guarantees for every domain are not gold, since no model can get them wrong. "Kernel" is
  the hand-built toolchain, and agent behavior the schema cannot express goes to the probe suite
  (ADR-0027). Examples:
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
| Unsupported rules | rules with no source and no confirmation (reported, no verdict) | — |
| Interview efficiency (ADR-0014, ADR-0025) | questions and minutes per stage; cells decided per question; share of cells decided by confirmed defaults | ① |
| Matrix completeness | share of (state, action) cells decided rather than `undecided`; cells decided through the interview vs. drafted from sources | reported |
| Harness findings | invariant violations and parity failures found before deploy, and by which part (cell tests, exploration, flows) | ① |
| Generated vs hand-built | share of each tool (authoring, delivery) that is generated; hand edits to generated code; the regeneration check (ADR-0028) | self-compile |
| Handoff (⑥ partial) | handoff-breaking changes caught at compile time; requests whose intent survives (checked by the probes, ADR-0031) | ⑥ |
| Cost | tokens, $, human minutes per stage and per change, **per domain** | all |

## Verdict rules

> ADR-0034: in M1 these are **pilot targets**. The numbers are reported against them to tune
> the checks and size M2's run; they are not evidence for ① or ⑥, and the claim-status
> table does not change on them. They are M2's starting point for the ① verdict.

- **Supports ①** (compile-time checking) requires **all** of:
  - Toprope pre-deploy recall ≥ 80% with precision ≥ 70%
  - the NL arm's recall at least 30 points lower
  - the structured-spec arm's recall at least 10 points lower (the compiler's contribution)
  - median iteration time ≤ 1 minute to a validated preview, with no hand edits to
    generated surfaces. The latency targets fit it: impact report ≤ 2 s, affected harness
    ≤ 30 s, preview ≤ 30 s.
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
- **Supports ⑥ (partial)**: every seeded handoff-breaking change is caught before deploy,
  and the probe that checks a handed-off request arrives intact (P07) passes. If the key
  seeds no handoff-breaking change, the result is "the handoff holds across the change
  sequence" when P07 passes, reported with "catching handoff-breaking changes was not
  tested". Otherwise inconclusive.
- **② is not judged in M1** (ADR-0030). Its verdict rules, held-out accuracy and the P0
  sanity check move to M2, on an application domain whose expert is not Toprope's builder.
- **Self-compile claim** (a feasibility result) holds only if all of these hold:
  - the tools used in S4 and handed to M2 are generated from the declarations, with hand
    edits listed (target 0)
  - the regeneration check (ADR-0028) passes
  - the probes pass (ADR-0031: the self domains have no gold set; the researcher confirms
    them in the interview and signs off)
  - the switch-over (ADR-0022) happens with the researcher's sign-off

## Risks

- **Seeding bias.** The people who build the checks also choose the seeded problems. This
  is why M1 is a pilot (ADR-0034) and the ① verdict moves to M2, where the change requests
  come from an expert who is not the builder. Still include problem types the checks were
  not designed for, and report per-type recall.
- **Unequal information.** The NL skill and the structured spec are written from the same
  confirmed model. A second reader checks that every rule appears in all three arms.
- **Circularity and self-approval.** The gold set, the change key and the verdict checks
  live outside the model and are never edited by the loop. "No agent can confirm" is itself
  a scenario.
- **Designer bias.** The self domain favors success. M2 repeats Phase B on a dogfood
  domain, and only M2 counts as evidence outside the self domain.
