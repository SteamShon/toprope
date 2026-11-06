# Status

Link: none (enabler). A snapshot of what is done and what is left, and nothing else. History
lives in git, the PRs and the ADRs; plans live in [`roadmap.md`](roadmap.md) and the milestone
and experiment docs. Every PR into `develop` or an `umbrella/*` branch updates this file, or
says why not; each release trims it ([`AGENTS.md`](../AGENTS.md), "Progress").

Updated: 2026-11-06 · Cleaned for release: `v0.1.0`

## Where we are

**M1** (self-compile; a pilot of ① and ⑥, no link verdict). M0a is done and released as
`v0.1.0`. No link has a verdict yet: every row of the README
[claim-status table](../README.md#claim-status) is `untested`.

## Done

- **M0a thin slice** (umbrella #15, released in #65): declarations and semantics, model
  interpreter, Execution and event stores, `toprope-server` MCP, authoring MCP, world map,
  harness, change check with log replay and in-flight check, incremental analysis, commits
  and branches (ADR-0029, ADR-0033).
- **M1 instruments, stage 1 in part:** the probe suite and verdict rules are frozen
  (`experiments/m1/instruments/FROZEN.json`).
- **M1 Phase A:** the Authoring and Delivery self domains are built and confirmed (#69, #73,
  #74), and their first commits are approved (#77).
- **Generated surfaces:** domain guide at preview (#67), the mechanical harness layer
  (ADR-0035, #71), the generated `toprope-run` command line and how-to-work guide (ADR-0036,
  #76), the domain commit store kept in git (#75).

## In progress

- **Switch-over** (ADR-0037, umbrella #81 into `develop`): only the kernel stays hand-built.
  - done: interview operations as kernel services (#80), per-domain layout and a JSONL event
    store in git (#82), the Authoring declaration calls the interview services (#83),
    `toprope-run` as yourself from your git identity (#85)
  - open: run the self domains end to end on the generated tools, with the regeneration
    check (#86)
  - left: remove `toprope-author`, `toprope-deploy`, their modules and hand-written guides;
    the researcher signs off

## Next

- **M1 instruments, the rest** (researcher): the change requests and the sealed change key,
  frozen before the pilot runs; then the binding, frozen after Phase A
  ([`experiments/m1/README.md`](../experiments/m1/README.md)).
- **M1 Phase B:** the change sequence on the three arms, then the M1 report
  ([`experiments/M1-self-compile.md`](experiments/M1-self-compile.md)).
- **Release M1** to `main`.

## Open questions

- None recorded.
