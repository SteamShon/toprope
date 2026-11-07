# toprope-harness

Link: ① ② ③ ④. The generated harness of ADR-0010, at the model, Execution and MCP levels
(M0a). A2UI view checks come in M0b.

```bash
uv run toprope-harness --domain my.domain.yaml                      # all levels
uv run toprope-harness --domain my.domain.yaml --levels model --examples 500 --json report.json
```

It exits 1 on any finding. From Python: `toprope.harness.run_harness(domain)` returns a
`Report` (`ok`, `findings`, `coverage`, `minimal_flows`, `summary()`, `to_json()`).

## The regeneration check (ADR-0028)
```bash
uv run toprope-harness --composition self.composition.yaml --regen-check
```
1. It serves every member from its declaration and runs the harness at every level.
2. It regenerates everything from the files and runs again.
3. The two runs must agree, and both must pass.
4. Each action that calls a kernel service is taken once, end to end, with a recording
   kernel. Its calls must be resolved and its replies accepted.

## What it runs

| Part | What it checks |
|---|---|
| **Small world** | Grown from the fixtures by applying allowed transitions (bounded BFS). One person per role, named after `world.actors`. Matrix states never reached are reported as `unreachable`. |
| **Cell tests** | Every (state, action, role) cell, from a world instance in that state. Expected outcomes come from the declared matrix, actor rules and preconditions, read directly rather than through the interpreter's decision, so these tests also check the oracle against the declaration. |
| **Param tests** | Each allowed cell, on every instance in its state, with one param of a finite type (boolean, enum, integer) set to each other candidate value. Expected outcomes come from the declaration; an invariant guard is a finding. A cell test takes the default params only, so a move that breaks an invariant only with another value (a kernel reply with `false`) went unseen until TLC found two (ADR-0043). |
| **Precondition tests** | For each precondition: an instance on which it is the first to fail (a boundary instance, such as `E-bare`). When no world instance is one, it is made from one by setting a single property or param the precondition reads to another value of its type, or to an actor's id, keeping every invariant. |
| **Create tests** | Every create action, for every role. |
| **Invariant checks** | After every step at every level. An `invariant-guard` outcome is reported as an invariant finding: the declaration allows a transition its invariants forbid. |
| **Parity** | Each outcome, each allowed-actions list and each stored event stream must equal the model level's. |
| **Replay parity** | Folding an object's stored events rebuilds exactly the state the command produced. |
| **Race tests** | Two actors on one cell at once, through Execution on a durable store. The pair of outcomes must be the outcome of one of the two serial orders, and the invariants must hold (`docs/semantics.md` §3). |
| **Bounded exploration** | Action sequences on the model level, bounded by depth and a fixed number of derandomized examples (Hypothesis `find`), never by wall-clock time. A violation is shrunk to a **minimal flow** in domain terms (who did what, from which state). |
| **Flows** | The declaration's `scenarios`, run as written at every level. A step by `{external: kernel}` states a kernel service's result. |
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
  `ref`, or a type default). A precondition test may set one param to another value.
- Clones carry their outgoing links. No other object links to a clone.
- Exploration runs on the model level. A minimal flow it finds can be replayed on the other
  levels like any other flow.
- Results are not cached yet. Incremental selection and the result cache come with
  sub-PR 9 (ADR-0013).

## Mutants: can the harness fail?
```bash
uv run toprope-harness --domain my.domain.yaml --mutants
```
A check never seen failing proves nothing. `--mutants` runs the harness once per seeded break,
given to the execution level only, while the model level and every expectation read the real
declaration. So each mutant stands for an implementation that drifted from the declaration:
- a skipped precondition;
- a role that may no longer act;
- a skipped `set` effect;
- a cell refused, retargeted to another state, or allowed where it was denied.

Each must be caught by some finding. A survivor is a break the harness cannot see, and the
command exits 1. Either a case is missing, or the mutant behaves like the declaration in every
state the harness can build (for example, a precondition that always holds).
`toprope.harness.mutants.run_mutants(domain)` returns the same report.

## Cross-check with TLC (ADR-0043)
```bash
uv run toprope-harness --domain my.domain.yaml --tla DIR    # the model level as TLA+, for TLC
python tools/tla_check.py --jar tla2tools.jar DECLARATION... # what the `tla` CI job runs
```
Exploration samples action sequences. TLC enumerates every reachable state of the exported model
and reports the shortest path to each broken invariant. Each path is replayed on the model level
from the same fixtures (`toprope.tla.replay`):
- **known**: reproduced, and the harness reports the same invariant broken. The harness fails on
  it already.
- **harness gap**: reproduced, and the harness missed it. Exploration did not reach the break.
- **model mismatch**: not reproduced. The export and the interpreter disagree on what the
  declaration says.

The `tla` job fails on a harness gap, a model mismatch, a model TLC cannot check, or a reached
state bound. It also requires a seeded break (`tests/tla/`) to be found and reproduced, so a
silent pass cannot mean that TLC checks nothing. Actions that create objects, use time or
follow links are left out of the model and listed with every run.

## The mechanical layer (ADR-0035)
Besides the examples, the harness generates objects from the declaration's types, enums and
links, in every stage, keeping only those that satisfy every invariant, and runs every
(stage, action, role) cell on them at every level. It needs no examples.
- **Parity** across levels on generated objects: a failure.
- **Not inductive**: from an object every invariant allows, a move the matrix allows breaks
  an invariant. Reported as a **warning** (`kind: inductive`, in `Report.warnings`): the
  start may be one no real history reaches, but nothing in the declaration rules it out.
  Strengthen an invariant (rule out the start) or a precondition (refuse the move).
- **Unreachable from creation**: stages no declared move reaches from the stage a created
  object starts in (a static walk of the matrix), reported apart from "unreachable from the
  examples".

Generation is seeded (3 objects per cell), so runs are reproducible and cached per action
by the incremental check (ADR-0013). The change check reports non-inductive invariants as
`harness` warnings and unreachable-from-creation stages as `semantic` warnings.

