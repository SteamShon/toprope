# ADR-0019: Thin slice first, milestone spec PRs, and a third M1 arm

- Link: all · Status: accepted · 2026-11-04 · decided by: SteamShon
- Origin: design review 2026-11-04 (findings 5–7, roadmap order)

## Context
M0 grew to 6–8 weeks, so the first verdict was about three months away. Yet M1 Phase B
needs only the declaration, the matrix, the model and Execution-level harness, the change
check and incremental analysis. It does not need UI, brownfield, hosting shapes or Aegra.
Two other review findings also land here: M3–M5 lack concrete requirements, and the M1
comparison cannot separate "having a structured spec" from "having a compiler".

## Decision
1. **Reorder.**
   - **M0a (thin slice)**: schema, matrix and invariants, the declaration semantics (below),
     model interpreter, Execution, event store, MCP via `toprope-server`, the authoring MCP,
     harness at the model, Execution and MCP levels, change check without log replay,
     incremental impact analysis.
   - **M1** runs on M0a.
   - **M0b** (UI and shell, representation compiler, brownfield adapter, embedded shape, log
     replay, in-flight check and migration) runs **after M1 and before M2**.
2. **Semantics before code.** `docs/semantics.md` defines evaluation order, atomicity,
   concurrency, time, identity and event shape. The model interpreter implements it, and it
   is the harness's oracle.
3. **Milestone spec PRs.** Before a milestone starts, a PR freezes its requirements, done
   criteria and verdict rules (researcher-frozen where AGENTS.md requires). No milestone
   starts without one.
4. **Third M1 arm.** Besides the NL skill arm and the Toprope arm, a **structured-spec arm**
   applies the same changes to the same YAML declaration, with an LLM review and no
   compiler. Comparing the arms separates three effects:
   - writing it down at all (NL vs. structured)
   - the compiler's checks (structured vs. Toprope).

## Consequences
- The time to the first verdict drops from about 12 weeks to about 6–7 weeks.
- M1's verdict rules gain the structured-spec arm. They are still a draft for the researcher
  to freeze.
