# M1 self domains: scope (DRAFT)

Link: ① ② ⑥ (partial). **Status: draft by the assistant; the researcher edits and confirms.**
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

**Out of scope:** running a domain's own work (that belongs to each domain); deploying
(Delivery); representation-only changes, which stay in Authoring but are light (ADR-0008).

**Candidate object types (vocabulary only):** Source, DraftElement (proposal), Question,
Answer, Confirmation, Unknown, DomainVersion, ChangeReport, Proposal, Decision.

**Actors:** the domain owner (person), domain experts (people), agents drafting and
interviewing on behalf of the owner (ADR-0016), and the system.

## Domain Delivery

**Purpose (draft).** An approved domain version becomes working software in a target
environment, and nothing unverified reaches it.
**Success metric (draft).** Share of approved versions that reach "verified in use"
without a manual fix or rollback (higher is better), and the time it takes.

**In scope:** receiving a delivery request; building artifacts (MCP, backend, views, harness,
world map); running the harness and change-check results as gates; preview; approval to
deploy; deploy and activate; in-flight checks and migration plans; post-deploy verification
(read-back, first use); rollback or roll-forward.

**Out of scope:** deciding what the domain means (Authoring); running the domain's own
work.

**Candidate object types (vocabulary only):** DeliveryRequest, Build, HarnessRun, Preview,
DeployApproval, Deployment, Environment, MigrationPlan, Verification, Rollback.

**Actors:** the approver of deploys (person), the system (build, harness and timers),
agents preparing builds on behalf of a person, and the effect adapters (kernel pipeline,
hosts).

## The handoff contract (Authoring → Delivery)

- **Trigger:** Authoring approves a `DomainVersion`.
- **Request:** Authoring calls Delivery's published `request_delivery`. The request carries
  the domain id, the version, the interface version, the change report reference, the
  target environment, and the approver.
- **Contract:** Delivery publishes this action and its params through its domain interface
  (ADR-0008, ADR-0023). Authoring can only send what that interface accepts. A change to
  the interface that removes or renames something is a major bump and breaks the handoff at
  compile time.
- **Feedback:** Delivery's outcome (`verified`, `rolled back`, `rejected`) is readable by
  Authoring through query tools, and can become evidence for proposals (⑤).

## Bootstrap (ADR-0022)
The hand-built kernel pipeline stays the source of truth for deploys until the generated
Delivery tool passes its harness. After that, the kernel pipeline becomes Delivery's effect
adapter, and its deploy gate stays as the floor.

## For the researcher to decide when confirming
- Keep, rename or drop the candidate object types (they only seed the interview vocabulary).
- Whether Toprope's components (core, compilers, server, shell) are part of Delivery's
  `Build` (ADR-0020's structure layer), or stay out of scope.
- The two purposes and success metrics.
- How the gold set and change sequence split across the two domains, decided when freezing
  the M1 instruments.
