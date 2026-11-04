# ADR-0023: Schema v1: the whole declaration language, defined up front

- Link: ① ② ③ ④ · Status: accepted · 2026-11-04 · decided by: SteamShon
- Amends: ADR-0015 ("added to docs/domain-schema.md when implemented, not before"), ADR-0014

## Context
The language was spread over ADR-0004, 0008, 0010, 0012, 0015, 0016, 0021 and 0022, and several
constructs were deferred until they were implemented. A full review of the language was not
possible, and later constructs risked colliding with earlier ones.

## Decision
1. **Define all of it now.** `docs/domain-schema.md` is the single reference for schema v1. It
   covers core constructs, purpose, handoffs, approvals, cross-aggregate invariants with
   reservations, timers and `advance` steps, functions, external sources, actors and agents,
   and the representation layer.
2. **Machine-readable schemas** `schema/domain.v1.schema.json` and
   `schema/representation.v1.schema.json` are generated from `tools/gen_schema.py`. A test
   validates every YAML example in the reference against them.
3. **Status per construct.** Each one is *implemented* (M0a), *M1* or *defined* (M0b). A
   construct that is defined but not implemented is **refused by the kernel with an explicit
   "not implemented until …" error**, never ignored. That matters most for `scope: cross`
   invariants, which would otherwise fail open.
4. **Purpose** (problem, one success metric, a pre-build announcement) is added as metadata,
   following the "product gate" practice of writing the announcement before building
   (Dex Horthy's software-factory playbook). The interview opens with it (amends ADR-0014).
   It never changes behavior.
5. **Language growth** after v1 needs an ADR and a schema bump. Domains grow inside the
   language (P0); the language itself changes deliberately.

## Consequences
- The kernel models know every v1 key. Unimplemented ones are validation errors that name
  their milestone.
- M0b and M1 implement constructs against fixed syntax, so no renaming churn.
