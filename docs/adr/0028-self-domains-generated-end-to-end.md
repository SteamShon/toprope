# ADR-0028: Self domains are generated end to end: kernel services as declared effects

- Link: ① iterate safely, ② model is right, ③ works as built · Status: accepted · 2026-11-04 ·
  decided by: SteamShon
- Amends: ADR-0019 (M0a scope; the overrun rule is set aside for this addition by the
  researcher's decision), ADR-0023 (`external` is implemented for the one source `kernel`
  in M0a), ADR-0024 (effects use the same outbox as handoffs)
- Builds on: ADR-0002 (self-compile), ADR-0022 (two self domains), ADR-0027 (the kernel)

## Context
Domain Authoring and Domain Delivery must iterate in M1: change the declaration, regenerate,
and the tools still work. That holds only if **everything** they do comes from their
declarations, with no hand-written glue in between.

Today the state, actions, permissions and matrix are generated (MCP tools, harness, world
map), and so is the wiring between domains (ADR-0026). The **work itself** is not: compiling,
running the harness, reading and redacting sources, previewing and deploying. So is not
**turning that work's results into state**, for example "the draft has 3 conflicts, so the
next stage is closed". Hand-built tools do both: `toprope-author` with its stage logic, and
`toprope-deploy`.

Schema v1 defines `effects` adapters and `external:` actors, but they were planned for M0b,
after M1. M1's generated tools could then only manage state, and hand glue would sit between
them and the kernel. Regenerating after a declaration change would break exactly there.

## Decision
1. **Generated end to end.** Every domain, the self domains first, is served from its
   declaration (and its composition) plus the kernel (ADR-0027) and nothing else. Hand-built
   domain tools such as `toprope-author`'s workflow and stage logic are bootstrap only. They
   are retired at the M1 switch-over (ADR-0022), when the generated tools take over.
2. **Kernel services are called as declared effects.** An action may call a service from a
   fixed catalog, and names the action that receives the result:
   ```yaml
   actions:
     check_version:
       actor: [owner]
       target: DomainVersion
       effects:
         - call: run_harness                      # a kernel service
           with: {version: target.id}             # inputs: check-language expressions
           reply: record_harness_result           # the action that receives the result
     record_harness_result:
       actor: ["external:kernel"]
       target: DomainVersion
       params: {ok: {type: boolean}, findings: {type: integer}}
       effects:
         - set: {target.harness_ok: params.ok, target.findings: params.findings}
   ```
   The catalog is the kernel itself:
   - `validate`, `compile` and `check_composition`
   - `run_harness` and `world_map`
   - `read_source` (redacted, local-only respected) and `fetch_source`
   - `preview` and `deploy` (the fixed floor applies, ADR-0022)

   Each service has typed inputs and a typed result.
3. **Same outbox, same guarantees.** A call is appended as an `EffectRequested` outbox event,
   atomically with the action (ADR-0024). It is executed after the append. The result comes
   back as a command from the reserved actor `external:kernel` to the `reply` action, on the
   same target, keyed by the effect id, so it is applied at most once. The reply goes through
   the receiving domain's matrix, preconditions and invariants like any other command.
   Outcomes are recorded as `EffectSucceeded`, `EffectFailed` or `EffectUnknown`
   (`docs/semantics.md` step 12). A failed call still replies, with the failure in the
   result, so the declaration decides what a failure means.
4. **Checked at compile time.** For each call, the compiler checks:
   - the service exists and its inputs map
   - the `reply` action exists and targets the same object type
   - the reply allows `external:kernel`
   - the reply's params match the service's result type
5. **Results become state, so gates are declared.** A service's result lands in properties
   through the reply's `set` effects. Gates such as "the next stage is closed while the draft
   has conflicts" or "a version cannot be approved before its change report exists" are
   then ordinary matrix cells and preconditions. No hand-written stage logic is needed.
6. **Tested like everything else.** The harness runs effects against a deterministic
   **recording fake** of each service. Scenarios state results as ordinary steps by the
   external actor:
   ```yaml
   - {actor: {external: kernel}, do: record_harness_result, target: V1, params: {ok: false, findings: 2}}
   ```
   The real services run in preview and in use.
7. **A regeneration check proves it.** The check works from only the declarations, the
   composition and the kernel:
   1. serve the self domains (`toprope-server --composition`)
   2. run the harness and the scenarios at every level
   3. regenerate, and get the same results

   M1's verdict rule "no hand edits to generated code" is checked this way.
8. **Scope.** `external:` is implemented for the single source `kernel` in M0a. Other
   external sources, brownfield effect adapters, timers and functions stay in M0b.

## Consequences
- **M0a scope.** M0a gains one sub-PR, "kernel effects": the effect syntax and checks, the
  kernel-service port with real and fake adapters, `external:kernel`, multi-domain serving
  from a composition, and the regeneration check. M0a's target grows by about 1–2 weeks.
  The researcher set the overrun rule aside for this addition; for everything else it still
  applies.
- **What changes.** The schema status table and `docs/semantics.md` step 12 are updated in
  that sub-PR.
- **Bootstrap.** The bootstrap authoring tool remains until the switch-over. M1 Phase A
  produces the declarations that replace it.
