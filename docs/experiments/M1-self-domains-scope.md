# M1 self domains: scope

Link: ① ② ⑥ (partial). **Status: confirmed by the researcher (2026-11-04)**, as drafted by the
assistant, with the decisions below.
Per ADR-0022, this file fixes **what is in scope**, not how it behaves. It deliberately
contains **no matrices, invariants, preconditions or answers**, because M1 Phase A must
produce those from sources and the interview. Candidate names below are vocabulary for the
interview, not a declaration. Phase A may rename, merge or drop them.

## Domain Authoring

**Purpose (draft).** A domain owner can turn a workflow that lives in people's heads into a
declared domain, and change it safely, without writing code.
**Success metric (draft).** Human minutes from an owner's intent to a confirmed, compiled
domain version (lower is better).

**In scope:** collecting sources; drafting proposed elements from them; asking the owner
interview questions; recording answers; confirming or rejecting elements; marking unknowns;
compiling a candidate domain version; reading the change report and world-map diff; deciding
to approve a version; proposals mined from the event history (⑤, later).

**Also in scope:** representation-only changes, as a light path (ADR-0008).

**Out of scope:** running a domain's own work (that belongs to each domain); deploying
(Delivery).

**Candidate object types (vocabulary only):** Source, DraftElement (proposal), Question,
Answer, Confirmation, Unknown, DomainVersion, ChangeReport, Proposal, Decision.

**Actors:** the domain owner (person), domain experts (people), agents drafting and
interviewing on behalf of the owner (ADR-0016), and the system.

## Domain Delivery

**Purpose (draft).** An approved domain version becomes working software in a target
environment, and nothing unverified reaches it.
**Success metric (draft).** Share of approved versions that reach "verified in use"
without a manual fix or rollback (higher is better), and the time it takes.

**In scope for M1 (thin, decided):** receiving a delivery request; building artifacts (MCP,
harness, world map); running the harness and change-check results as gates; preview;
approval to deploy; deploy to a **local** environment; verification (harness and probes).

**Added in M2** (when M0b provides them): migration plans and in-flight handling,
post-deploy read-back, timers, rollback or roll-forward, views and the greenfield backend.

**Out of scope:** deciding what the domain means (Authoring); running the domain's own
work.

**Candidate object types (vocabulary only):** DeliveryRequest, Build, HarnessRun, Preview,
DeployApproval, Deployment, Environment, MigrationPlan, Verification, Rollback.

**Actors:** the approver of deploys (person), the system (build, harness and timers),
agents preparing builds on behalf of a person, and the effect adapters (kernel pipeline,
hosts).

## The handoff contract (Authoring → Delivery)

- **Trigger:** Authoring approves a domain version or a representation version.
- **Request:** Authoring calls a request action that Delivery publishes. What the request
  carries is for the researcher to confirm. The draft: domain id, domain version,
  representation version (a released UI is the pair, ADR-0008), interface version, change
  report reference, target environment, approver.
- **Contract:** Delivery publishes this action and its params through its domain interface
  (ADR-0008, schema v1). Authoring can only send what that interface accepts. A change to
  the interface that removes or renames something is a major bump and breaks the handoff at
  compile time.
- **Feedback:** Delivery's outcome is readable by Authoring, and can become evidence for
  proposals (⑤). Which outcomes exist is a Phase A output.

## Bootstrap (ADR-0022)
The hand-built kernel pipeline stays the source of truth for deploys until the researcher
signs off the switch-over. After that, the kernel pipeline becomes Delivery's effect
adapter, and the kernel keeps a fixed floor of deploy rules that no declaration can weaken.

## Decisions (researcher, 2026-11-04)
- **Delivery in M1 is thin** (see above). The rest comes in M2.
- **Switch-over at the end of M1**, with the researcher's sign-off, after the generated
  Delivery tool passes its harness and the frozen M1 gold and probe checks. From M2,
  deploys go through the generated Delivery domain, above the kernel's fixed floor.
- **Phase A may read this repository's ADRs and this scope document** as records (S2).
  Extracting rules from records is what S2 is for. To keep the measurement honest:
  held-out gold questions avoid facts stated verbatim in these documents, and first-draft
  accuracy (the P0 sanity check) is measured after S1, which sees the system only.
- The purposes, success metrics, candidate vocabulary and handoff fields above are
  **confirmed as drafted**.
- Toprope's components are **not** part of Delivery's `Build` in M1. ADR-0020's structure
  layer for Toprope itself waits.
- **Still open, decided when freezing the M1 instruments:** how the gold set, probe suite
  and change list split across the two domains, and whether handoff-breaking changes are
  seeded.
