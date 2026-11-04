# ADR-0027: What the kernel is, and what it is not

- Link: ② model is right, ③ works as built · Status: accepted · 2026-11-04 · decided by: SteamShon
- Clarifies: ADR-0013 (the toolchain), ADR-0022 (the kernel pipeline and the fixed floor)

## Context
"The kernel" is used across the ADRs: the toolchain hash (ADR-0013), the hand-built kernel
pipeline and the fixed floor (ADR-0022). The M1 gold set now depends on the word: a fact the
kernel guarantees for every domain is not gold, because no declaration can get it wrong.
Writing the gold set exposed two readings:
- A narrow one: Execution's semantics and the deploy floor only.
- The toolchain reading in ADR-0013: Execution, the compiler, the harness runtime.

Under the narrow reading, compiler facts (what a change report contains, how interface
versions bump) looked like declaration facts. Yet removing them from a declaration changes
nothing, so they could not measure anything.

## Decision
1. **The kernel is the hand-built Toprope toolchain.** It is the same set ADR-0013 hashes:
   - **Execution's semantics**: `docs/semantics.md`, covering the order of evaluation,
     matrix meaning, actor rules and `requires: human`, idempotency, the invariant guard,
     events, and the handoff outbox
   - **the compiler and the change check**: validation, the domain interface and its
     versioning, impact reports, previews, generated surfaces, and the world map
   - **the harness runtime**
   - **the fixed deploy floor**: `toprope-deploy`, ADR-0022
2. **Hand-built tools for the self domains are not the kernel.** An example is today's
   authoring tool (`toprope-author`). It is a bootstrap implementation of a domain's
   workflow (who drafts, asks, confirms, approves). M1 replaces it with a tool generated
   from the declared domain, so its rules are **declaration facts**. The kernel is invoked
   by such a workflow as an effect (compile, run the harness, deploy). It is never declared
   by it.
3. **Test for a borderline fact.** Ask: "if the declaration omitted or inverted this, would
   the compiled domain still give the same answer?"
   - **Yes**: a kernel fact.
   - **No**: a declaration fact.

   A fact that the declaration states *and* the kernel enforces (e.g. a person approves a
   deploy, which is also in the floor) is a kernel fact.
4. **What follows for the instruments.**
   - **Gold** holds declaration facts only. Each item is graded against the compiled domain,
     or against the composition (ADR-0026) for a fact that spans domains.
   - **Agent behavior the schema cannot express goes to the probe suite**, not to gold.
     Examples: asking conflicts first, bundling questions, redacting sources, recording
     which sources were used.
   - A kernel rule can still be asked about as a **gate in a domain's own workflow**, where
     the declaration decides it. For example: "can a version be approved before its change
     report exists?"

## Consequences
- `docs/experiments/M1-self-compile.md`, the M1 instrument guide and the gold template cite
  this ADR for "kernel".
- The toolchain hash (ADR-0013) and the kernel are the same set, so a kernel change
  invalidates cached results and harness-based approvals alike.
