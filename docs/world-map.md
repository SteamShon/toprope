# World map

Link: ④ ①. The compiled "skill tree" of ADR-0020: a deterministic graph built only from the
declaration and, optionally, the build's harness results. It is a view and never adds rules.

```bash
uv run toprope-worldmap --domain my.domain.yaml --out world-map.json --harness --mermaid docs/map
uv run toprope-harness --domain my.domain.yaml --json harness.json
uv run toprope-server --domain my.domain.yaml --identity static:tokens.yaml --harness-report harness.json
```

## `world-map.json` (`format: toprope.world-map/1`)
- `structure`: object types (`nodes`) and declared links (`edges`: from, to, cardinality,
  required), each with its element `status`.
- `behavior.states`: every matrix state of every stateful object, with `initial` and
  `terminal` (no outgoing transition).
- `behavior.roles` (with the world's people) and `behavior.system_actors`.
- `behavior.edges`: one per (state, action) cell, plus `(new) → initial` for create actions.
  Each edge has:
  - `outcome`: `to`, `deny` (with its reason), `n/a`, `undecided`, or `by_role` (per role)
  - `fog`: true when the cell is `undecided`
  - `unlock`: actor rules (with `where`), preconditions (id, reason, check),
    `requires_human`, plus `approvals` and `reservations` (empty until M0b)
  - `invariants`: those on the object that read a field the action writes
  - `records_decision`
  - `harness`: `verified`, `failed`, `uncovered` or `unknown` (no report)
- `unreachable`: states the harness's small world never reached.

Not yet emitted: usage heat from the event store (optional in ADR-0020), timers and
external events (`fired_by` is empty until M0b), and the map diff in impact reports
(sub-PR 9 and M0b).

## MCP tools
- `world_map`: the map above (read-only; it holds only the declaration and harness results).
- `how_to_reach(object_id, target_state)`: the shortest sequence of actions from the
  object's current state, who may take each step, and `you_can` for the caller. It prefers
  a path the caller can take. For an agent, only roles its principal also holds count.
  Preconditions are listed and checked at call time.

## Mermaid
`to_mermaid(map)` gives a flowchart of the structure layer and a state diagram per stateful
object. Undecided cells appear as notes.
