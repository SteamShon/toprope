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
     source readers, harness at the model, Execution and MCP levels, the change check
     **including log replay and the in-flight check** (M1 seeds changes that break past
     logs and strand objects), and incremental impact analysis.
   - **M1** runs on M0a.
   - **M0b** (UI and shell, representation compiler, brownfield adapter, embedded shape,
     migration plans, query tools, timers and functions) runs **after M1 and before M2**.
     After M0b, the self domain's authoring UI is regenerated from the same declaration.
2. **Semantics before code.** `docs/semantics.md` defines evaluation order, atomicity,
   concurrency, time, identity and event shape. The model interpreter implements it, and it
   is the harness's oracle.
3. **Milestone spec PRs.** Before a milestone starts, a PR freezes its requirements, done
   criteria and verdict rules (researcher-frozen where AGENTS.md requires). No milestone
   starts without one.
4. **Third M1 arm.** Besides the NL skill arm and the Toprope arm, a **structured-spec arm**
   applies the same changes to the same YAML declaration, with an LLM review and no
   compiler. Comparing the arms gives three numbers:
   - the effect of writing the domain down in a structured form (NL vs. structured)
   - the effect of the compiler's checks (structured vs. Toprope)
   - the total (NL vs. Toprope).

## Consequences
- The time to the first verdict drops from about 14 weeks (M0 6–8 + M1 3–4, plus the
  growth since) to about **8–9 weeks**: M0a, re-estimated at 4–5 weeks after it absorbed
  semantics, identity, the authoring MCP and the world map, plus M1 at 3–4 weeks. This is a
  target at about 10 h/week, not a commitment.
- M1's verdict rules gain the structured-spec arm. They are still a draft for the researcher
  to freeze.
