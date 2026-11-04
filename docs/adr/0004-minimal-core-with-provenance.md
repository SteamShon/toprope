# ADR-0004: Minimal domain core (Object, Link, Action) with provenance and status

- Link: ① ② · Status: accepted · 2026-11-04 · decided by: SteamShon

## Decision
Start with Object, Link and Action. Every element carries `source` (system | record |
interview | use) and `status` (proposed | confirmed | unknown). Agents write only
`proposed`, and only humans confirm. Policy, contract and flow are added only when a
milestone needs them, each with its own ADR. See docs/domain-schema.md.
