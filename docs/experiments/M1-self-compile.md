# M1: Self-compile, and safe iteration vs. natural-language skills

Link: ① iterate safely, ⑥ (partial, the handoff); self-compile feasibility. ② model is right
moved to M2 (ADR-0030). Status: design draft.

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
| Correctness set | the small frozen set for the self tools' critical rules (ADR-0030); a guard on the tool M2 depends on, not a ② verdict | self-compile, ⑥ |
| Unsupported rules | rules with no source and no confirmation (reported, no verdict) | — |
| Interview efficiency (ADR-0014, ADR-0025) | questions and minutes per stage; cells decided per question; share of cells decided by confirmed defaults | ① |
| Matrix completeness | share of (state, action) cells decided rather than `undecided`; cells decided through the interview vs. drafted from sources | reported |
| Harness findings | invariant violations and parity failures found before deploy, and by which part (cell tests, exploration, flows) | ① |
| Generated vs hand-built | share of each tool (authoring, delivery) that is generated; hand edits to generated code; the regeneration check (ADR-0028) | self-compile |
| Handoff (⑥ partial) | handoff-breaking changes caught at compile time; requests whose intent survives (checked by the correctness set) | ⑥ |
| Cost | tokens, $, human minutes per stage and per change, **per domain** | all |

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
- **② is not judged in M1** (ADR-0030). Its verdict rules, held-out accuracy and the P0
  sanity check move to M2, on an application domain whose expert is not Toprope's builder.
- **Self-compile claim** (a feasibility result) holds only if all of these hold:
  - the tools used in S4 and handed to M2 are generated from the declarations, with hand
    edits listed (target 0)
  - the regeneration check (ADR-0028) passes
  - the correctness set passes
  - the switch-over (ADR-0022) happens with the researcher's sign-off

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
