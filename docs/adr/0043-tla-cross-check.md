# ADR-0043: Cross-check the harness with TLC

- Link: ③ works as built · Status: accepted · 2026-11-07 · decided by: SteamShon (the
  recommendation in each case; drafted by the assistant)
- Builds on: ADR-0010 (the generated harness), ADR-0035 (mechanical tests without examples),
  ADR-0021 (semantics clarifications from the oracle)

## Context
The harness checks a declaration against itself and its levels (`docs/harness.md`). Its search
for a broken invariant is **bounded exploration**: derandomized sequences of at most a few steps
from the small world. Harness mutants (#126) showed what a check never seen failing misses: three
preconditions in the examples could be skipped without any finding. Exploration has the same
risk at a larger scale. A state that breaks an invariant only after a longer path, or only from
a start the small world does not hold, is not found, and nothing reports that it was not looked
for.

A model checker answers the question exploration samples: TLC enumerates **every** reachable
state of a finite model and reports the shortest path to each broken invariant. It is a second
oracle, written separately from the interpreter, so the two can disagree, and a disagreement
always means a bug in one of them.

## Decision

1. **What is modeled: one declaration's model level.**
   - The initial states are the world fixtures. There is one actor per role, named as the
     harness names them (`world_actors`).
   - A step is an action taken by an actor on an instance, with param values. The step follows
     the declared matrix (including `by_role`), the actor rules, the preconditions and the `set`
     effects.
   - Invariants are TLA+ `INVARIANT`s. As in the harness, a step that would break an invariant is
     not refused in the model. That step is the finding: the declaration allows a transition its
     invariants forbid. The interpreter's invariant guard turns the same step into
     `invariant-guard`.
   - Params range over finite candidates, the same as the mechanical layer's: enum values, fixture
     ids for a `ref`, a few values per type, and the actors' ids for strings.
   - Kernel calls and handoffs are outbox events, not state changes (the interpreter only
     records them), so they are outside the model while the action that sets them off is in it. A
     kernel's reply is an action of the `external:kernel` actor, modeled like any other.
   - **Not modeled at first:**
     - time (`now()`, `days_since`);
     - paths through links to another object;
     - creating objects.

     An action whose guard or effect uses one of these is **left out of the model**. The report
     names it. So every counterexample TLC finds is a path the declaration allows, but a break
     reachable only through a left-out action is not found, and the report says which actions
     were left out. The alternative, treating such a guard as true, finds more and also reports
     paths that cannot happen. It was rejected.
2. **Where TLC runs: a `tla` CI job.**
   - TLC version 1.8.0 (`tla2tools.jar` from the `tlaplus/tlaplus` releases) is pinned by version
     and sha256.
   - The job is separate from `tests`, so the default test run needs no Java.
   - The exporter (Python, in the kernel) and its tests run in `tests`. TLC itself runs only in
     `tla`.
   - An agent's cloud session cannot run a downloaded jar, so work on the model goes through the
     job and its logs.
3. **What a finding is: replay decides.**
   - Each counterexample TLC reports is replayed, step by step, on the model-level interpreter
     from the same fixtures. This is pstack's `statechart` rule: a model's bug path is replayed on
     the real code, and one that does not reproduce means the model is wrong.
     - **Reproduced** (each step `ok`, the last one `invariant-guard`) and not among the
       harness's findings: a **harness gap**. Exploration missed a reachable break.
     - **Not reproduced:** a **model mismatch**. The exporter, or the interpreter, does not mean
       what the declaration says.
     - Reproduced, and the harness also found it: the declaration's break, already reported. The
       `tla` job does not count it twice.
   - A harness gap or a model mismatch fails the job. TLC is deterministic, so the job is
     blocking from the start. Making it a required check on `develop` is the maintainer's, once it
     is green there.
4. **Which declarations: every example and both self domains.**
   - Each runs under a bound on distinct states (1,000,000).
   - A declaration that hits the bound is reported **not checked** and fails the job. A bound
     reached is never read as a pass.

## Consequences
- `toprope.tla` exports a declaration to a `.tla` module and a `.cfg`. `toprope-harness --tla
  DIR` writes them, with the list of actions left out. `tools/tla_check.py` runs TLC and replays
  each counterexample (`toprope.tla.replay`), printing its verdict.
- Each run of the model starts from one fixture: no modeled step or invariant reads another
  instance, so checking them one at a time reaches the same states, in a sum instead of a product
  (`docs/harness.md`). Modeling links ends this.
- The expression language maps to TLA+ through tagged values that keep its fail-closed meaning: a
  missing attribute is null, and an operator on the wrong type gives an error value, so the check
  fails. TLC never stops on a type error that the interpreter treats as a failed check.
- The world map's state charts (#125) can later draw TLC's state graph. Not in this ADR.
- What is modeled grows by later ADRs or PRs: time, links, creation. Each one shrinks the list of
  actions left out.

## Implementation (umbrella #135)
One sub-PR each: this ADR; the exporter; the `tla` job; replay and verdicts; every example and
both self domains.
