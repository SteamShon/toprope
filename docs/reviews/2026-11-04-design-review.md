# Design review, 2026-11-04

Scope: all ADRs (0001–0013) and docs on `develop` after PR #8. The question was whether
this design, once implemented, reaches the goal, and what was overlooked.

## Verdict
The direction holds. The claim chain, the matrix and invariant harness, change safety and
event sourcing fit together. The weakest parts were the two that decide the outcome most:
**the interview** (the cost of ① and ②) and **what a state machine cannot express** (the
meaning of ③). The roadmap also put about three months of building before the first
verdict.

## Findings and resolutions
| # | Finding | Resolution |
|---|---|---|
| 1 | No interview design; the matrix grows as states × actions × roles | ADR-0014: defaults, grouped cells, priorities, stop rule, privacy |
| 2 | No time, cross-aggregate invariants, functions, external events or multi-party approval | ADR-0015 |
| 3 | Roles only; no relations, delegation or agent identity | ADR-0016 |
| 4 | Live-data migration deferred, though M2 needs it | ADR-0018 |
| 5 | No formal semantics; no concurrency tests; the harness oracle was undefined | `docs/semantics.md` (ADR-0019) |
| 6 | M1 could not separate "structured spec" from "compiler" | ADR-0019: third, structured-spec arm |
| 7 | M3–M5 requirements thin | ADR-0019: milestone spec PRs |
| 8 | Hosting: library vs. server; whether Aegra, Temporal and a host app were all required | ADR-0017: core library, server first, shell, optional runtime |
| 9 | M0 too broad before the first verdict | ADR-0019: M0a thin slice → M1 → M0b → M2 |
| 10 | A2UI preview risk; non-developer review UI before self-compile | ADR-0017 fallback; the CLI/YAML limit is stated in the roadmap |
