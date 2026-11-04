# ADR-0009: M1 tests H-Shared (shared language)

- Status: **superseded by [ADR-0011](0011-claim-chain-and-load-bearing-bet.md)** (now M2) · 2026-11-04 · decided by: SteamShon
- Supersedes: ADR-0003

## Decision
M1 compares docs plus generic tools (C0), hand-written typed tools with prose rules (C1),
and capsule-generated MCP (C2) on workflow-meaning errors. See
docs/experiments/M1-shared-language.md. Lessons from reviewing the superseded M1 design are
kept as principles: the strongest fair baseline, a non-tautological primary metric (intent
errors, not effects), a pilot gate, a cost estimate, and a fair revision probe.
