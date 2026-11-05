# ADR-0022: Two self domains: Domain Authoring and Domain Delivery, joined by a typed handoff

- Link: ① ② ③ ⑥ (partial) · Status: accepted · 2026-11-04 · decided by: SteamShon
- Amends: ADR-0002 (the first domain is now two self domains)

## Context
The researcher's intent was always two self domains, both built through the interview:
- **Domain Authoring**: making and changing a domain from sources, interviews and use.
- **Domain Delivery**: turning an approved domain version into delivered software, i.e.
  check → preview → approve → deploy → activate → verify, with rollback.

The plan modeled only Authoring as a domain. Delivery (change check, deploy gate, migration,
preview) was planned as hand-built kernel pipeline (M0a/M0b), so the Authoring/Delivery
split from the prior work had disappeared.

## Decision
1. **M1 self-compile covers both domains.** Each is built through the same pipeline
   (system → records → interview → use), measured with the same instruments, and compiled
   into its own generated tool (authoring MCP and delivery MCP).
2. **A typed handoff joins them.** When Authoring approves a domain version, it hands a
   delivery request to Delivery through Delivery's published domain interface. This is the
   first typed handoff, so part of ⑥ (H-Handoff) can be observed inside the self domains
   before M5.
3. **Delivery rules become declared state.** They get a matrix, invariants, the harness and
   event history like any other domain. Which rules they are is an output of M1 Phase A, not
   of this ADR.
4. **Bootstrap, staged.** Until the switch-over (below), the hand-built kernel pipeline stays
   the source of truth for deploys. After it, deploys go through the generated Delivery
   domain, and the kernel pipeline becomes its effect adapter.
   - **A fixed floor outside the loop.** The kernel keeps a small set of deploy rules in
     code, which no Delivery declaration can weaken: a harness pass at current hashes, no
     taint, no stranded objects without a tested migration plan, and a person approving.
     A harness generated from a Delivery declaration proves conformance to that
     declaration, not that it is right, so the floor cannot live in the declaration.
   - **Changes to the Delivery domain itself** are deployed only through the floor, with
     the researcher's sign-off. Delivery never approves its own changes.
   - **Switch-over** happens **at the end of M1**, when the researcher signs off after the
     generated Delivery tool passes its harness and the frozen M1 gold and probe checks for
     Delivery. In M1, Delivery is thin; migrations, read-back, timers and rollback join it in
     M2 (scope document).
5. **Scope is the researcher's, the rules are the experiment's.** The boundary, candidate
   object types and the handoff contract are written down before M1 (assistant drafts, the
   researcher confirms): `docs/experiments/M1-self-domains-scope.md`. Matrices, invariants
   and answers are not written in advance, because Phase A must produce them.

## Consequences
- (ADR-0030) M1 judges ① and ⑥ (partial) on the self domains, and reports self-compile as a
  feasibility result. ② is judged in M2 on an application domain.
- M1 grows: two Phase A builds, and the change sequence and gold set cover both domains (the
  researcher's call when freezing). The M1 estimate is revisited in M1's spec PR.
- The language needs a handoff construct, defined in schema v1 (`docs/domain-schema.md`).
- The kernel's change check and deploy gate (M0a/M0b) are still built as code. They are the
  bootstrap, and later the effect adapter of the Delivery domain.
