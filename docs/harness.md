# toprope-harness

Link: ① ② ③ ④. The generated harness of ADR-0010, at the model, Execution and MCP levels
(M0a). A2UI view checks come in M0b.

```bash
uv run toprope-harness --domain my.domain.yaml                      # all levels
uv run toprope-harness --domain my.domain.yaml --levels model --examples 500 --json report.json
```

It exits 1 on any finding. From Python: `toprope.harness.run_harness(domain)` returns a
`Report` (`ok`, `findings`, `coverage`, `minimal_flows`, `summary()`, `to_json()`).

## What it runs

| Part | What it checks |
|---|---|
| **Small world** | Grown from the fixtures by applying allowed transitions (bounded BFS). One person per role, named after `world.actors`. Matrix states never reached are reported as `unreachable`. |
| **Cell tests** | Every (state, action, role) cell, from a world instance in that state. Expected outcomes come from the declared matrix, actor rules and preconditions, read directly rather than through the interpreter's decision, so these tests also check the oracle against the declaration. |
| **Precondition tests** | For each non-state precondition that does not read `params`: a world instance on which it is the first to fail (a boundary instance, such as `E-bare`). |
| **Create tests** | Every create action, for every role. |
| **Invariant checks** | After every step at every level. An `invariant-guard` outcome is reported as an invariant finding: the declaration allows a transition its invariants forbid. |
| **Parity** | Each outcome, each allowed-actions list and each stored event stream must equal the model level's. |
| **Replay parity** | Folding an object's stored events rebuilds exactly the state the command produced. |
| **Race tests** | Two actors on one cell at once, through Execution on a durable store. The pair of outcomes must be the outcome of one of the two serial orders, and the invariants must hold (`docs/semantics.md` §3). |
| **Bounded exploration** | Action sequences on the model level, bounded by depth and a fixed number of derandomized examples (Hypothesis `find`), never by wall-clock time. A violation is shrunk to a **minimal flow** in domain terms (who did what, from which state). |
| **Flows** | The declaration's `scenarios`, run as written at every level. |
| **Coverage** | Decided cells covered per level, undecided cells, cells with no instance (gaps), precondition boundaries, invariants exercised, flows passed, race tests, unreachable states. |

Each case runs on its own clone of a world instance (`<id>~h<n>`), so cases never
interfere. Setup loads clones as fixtures and is not under test. Every action and read under
test goes through the level's own surface, which for MCP means the generated tools.

A finding (a failing cell test, an invariant violation, a parity, replay or race failure, a
failing flow, or an exploration counterexample) fails the run. Coverage gaps are reported
and do not fail it: they are the interview's next questions (ADR-0010 §2).

## Limits in M0a
- Cell tests use one person per role. Agents (principal and grant) are covered by the
  Execution and MCP tests, but are not yet in the generated cells.
- Each required param gets one default value (the first enum value, the first fixture of a
  `ref`, or a type default). Preconditions that read `params` are exercised only with it.
- Clones carry their outgoing links. No other object links to a clone.
- Exploration runs on the model level. A minimal flow it finds can be replayed on the other
  levels like any other flow.
- Results are not cached yet. Incremental selection and the result cache come with
  sub-PR 9 (ADR-0013).
