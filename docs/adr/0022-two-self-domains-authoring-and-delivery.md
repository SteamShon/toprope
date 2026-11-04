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
3. **Delivery rules become declared state.** Examples: a build with a failing harness, taint
   or stranded objects without a plan cannot be deployed. They get a matrix, invariants, the
   harness and event history like any other domain.
4. **Bootstrap, staged.** Until the generated Delivery tool passes its own harness, the
   hand-built kernel pipeline (M0a/M0b) stays the source of truth for deploys. After that,
   deploys go through the generated Delivery domain, and the kernel pipeline becomes its
   effect adapter. The kernel's deploy gate is never removed, so a broken Delivery
   declaration cannot deploy itself (no self-approval, ADR-0016).
5. **Scope is the researcher's, the rules are the experiment's.** The boundary, candidate
   object types and the handoff contract are written down before M1 (assistant drafts, the
   researcher confirms): `docs/experiments/M1-self-domains-scope.md`. Matrices, invariants
   and answers are not written in advance, because Phase A must produce them.

## Consequences
- M1 grows: two Phase A builds, and the change sequence and gold set cover both domains (the
  researcher's call when freezing). The M1 estimate is revisited in M1's spec PR.
- The language needs a handoff construct, defined in the schema v1 (ADR-0023).
- The kernel's change check and deploy gate (M0a/M0b) are still built as code. They are the
  bootstrap, and later the effect adapter of the Delivery domain.
