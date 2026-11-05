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
  - `hands_off`: the handoffs this action sends (domain, interface, action), ADR-0024
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

## The domain guide
Next to `world-map.json`, a preview writes `domain-guide.md`: the same domain told for people,
in the terms of [`domain-model.md`](domain-model.md). It covers purpose, roles, objects and
links, an action table (who, on what, what must be true first, what it changes, what it
starts, its event), the transition matrix per object with its undecided cells, invariants,
examples and scenarios, handoffs, and what is generated (MCP tools, events, harness
coverage). It is generated from the declaration and never edited by hand.
`toprope-worldmap --domain d.domain.yaml --guide domain-guide.md` writes it on its own.

