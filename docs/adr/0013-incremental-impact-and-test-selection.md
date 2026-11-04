# ADR-0013: Incremental rebuilds: precise impact analysis and affected-only testing

- Link: ① iterate safely · Status: accepted · 2026-11-04 · decided by: SteamShon

## Context
Domains are found by iterating (P0), so the loop runs constantly. If every declaration
change reruns the whole harness, a test run takes ten minutes and trying a change takes five,
and nobody will iterate. Developer experience requires knowing **exactly** what a change
affects, and rerunning only that.

Toprope has an advantage here. All code and every test are generated from the
declaration, so dependencies are known **statically**, from the declaration itself. They do
not have to be guessed from a call graph.

## Decision

### 1. One dependency graph, from declaration to tests
The compiler keeps a graph from each declaration element to everything derived from it:

```
element (object, field, link, action, matrix cell, invariant, glossary term, view, fixture, flow)
   → generated artifacts (MCP tool, A2UI view, backend route, event schema, projection, upcaster)
   → tests (cell tests, invariant checks, flows, view checks, replay checks, adapter checks)
```

- Every element and artifact has a **content hash**.
- Dependencies of `check` expressions (preconditions, invariants) come from the paths they
  read. If an expression cannot be analyzed precisely, it depends on the whole object. This
  is conservative: when the analysis is unsure, it over-selects. It never under-selects.
- Small-world instances record which fixtures and transitions produced them.

### 2. Impact analysis is the first step of every change check
1. Diff the declaration.
2. Find the changed elements.
3. Walk the graph to the affected artifacts and tests.
4. Show an **impact report** in domain terms *before* anything runs. For example: "changes 2
   matrix cells; affects 14 cell tests, 1 invariant, 2 views and 3 flows; replays 41 past
   events of type ExperimentApproved".

### 3. Only the affected set runs; results are cached
- Rebuild only affected artifacts. Unchanged artifacts are reused by hash.
- Each test result is cached under the hashes of all its inputs: the elements, artifacts,
  fixtures and seed it depends on. A test whose inputs did not change is a **cache hit** and
  does not run again.
- Bounded exploration (ADR-0010) is scoped to the affected cells and invariants, under a
  time budget, while the author is iterating. Deeper exploration runs in the background and
  reports later.
- Log replay (ADR-0009) replays only the events whose types, or whose target objects' cells,
  are affected.
- A representation-only change touches only the UI-level tests of the affected views
  (ADR-0008).

### 4. Deploy gate and soundness
- **Deploy gate.** Deployment requires every test to have a passing result for the current
  input hashes. Most of these are cache hits, so the gate is incremental too. Nothing is
  skipped. Unaffected tests are only *not re-run*.
- **Soundness check.** A full uncached run happens in the background (e.g. nightly, and
  before each release PR). Any test that fails there but was passing from cache is a
  **selection miss**: a bug in impact analysis. It is fixed as a priority.

### 5. Latency targets (initial, drafted by the assistant, for the researcher to confirm)
| Step | Target for a typical single change |
|---|---|
| Impact report | ≤ 2 s |
| Affected harness (excluding background exploration) | ≤ 30 s |
| Preview build ready to try | ≤ 60 s |
| Full uncached run | no target; runs in the background |

## Consequences
- The compiler is designed incremental from M0: hashes, the graph, the cache and the impact
  report are part of the kernel, not later optimizations.
- New ports: `ImpactAnalyzer` (graph and affected set), `ResultCache` (test results keyed by
  input hashes).
- M1 measures iteration time per step and the selection-miss count.
