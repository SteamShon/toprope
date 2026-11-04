# ADR-0012: Raw material order: system → records → interview → use

- Status: accepted · 2026-11-04 · decided by: SteamShon

## Decision
All four sources are supported. They are used in order of how easily they can be automated:
draft from existing systems (code, schema, APIs), enrich from existing records (docs,
issues, chats), raise accuracy by interviewing the owner, and keep improving through use.
Every model element records which source it came from and whether a human confirmed it.

## Consequences
M1 measures each stage's contribution, which tests whether this order is right.
