# ADR-0020: The world map, a compiled "skill tree" of the whole domain

- Link: ④ shared language, ① iterate safely · Status: accepted · 2026-11-04 · decided by: SteamShon

## Context
People and agents need to see the **whole** world at once: every state, every transition,
who can take it, and what is required to unlock it. Today that picture lives only inside the
declaration and the harness. The researcher's image is a game skill tree (as in Diablo).
From where you stand, you see which actions are unlocked, which are locked and what unlocks
them, and which parts of the map are still in fog.

Toprope's own components and authoring workflow can be declared as a Toprope domain
(self-compile, ADR-0002). So the same map can also show Toprope itself.

## Decision

### 1. A compile output, deterministic
The domain compiler emits `world-map.json`, a graph derived only from the declaration plus
the build's harness results:
- **Nodes**: the states of each stateful object (and terminal states), roles and actors
  (persons, agents with grants, system/external), and linked objects.
- **Edges**: one per (state, action) cell, with its outcome: target state, `deny`, `n/a` or
  `undecided`. Each edge also carries:
  - its **unlock requirements**: the role or relation, the non-state preconditions,
    approvals, reservations, and `requires: human`
  - the invariants it touches, and whether it records a decision
  - timers and external events that can fire it.
- **Status overlays**:
  - element status: confirmed, proposed or unknown; `undecided` cells are drawn as **fog**
  - harness status per edge: verified, failed or uncovered (ADR-0010)
  - optionally, **usage heat** from the event store: attempts, denials and exceptions per
    cell (ADR-0012).

It is part of the domain capsule and is rebuilt incrementally like any other artifact
(ADR-0013).

### 2. Three views of the same map
- **Skill-tree view** in `toprope-shell`. Pick an actor (a role, a person, or an agent with
  a grant) and an object in a state:
  - unlocked actions are lit
  - locked actions show exactly what would unlock them ("needs role approver", "needs ≥ 1
    guardrail")
  - fog marks undecided cells.

  It can also answer **path questions**: "how does an experiment get from `draft` to
  `decided`, and who must act at each step?"
- **Agent view**: the generated MCP exposes `world_map` (read-only) and
  `how_to_reach(object, target_state, actor)`. Agents plan within the same map people see
  (④).
- **Docs view**: a Mermaid export (state diagrams per object, plus a component graph), so
  documentation embeds generated diagrams instead of hand-drawn ones.

### 3. World-map diff in every impact report
A change's impact report (ADR-0013) includes the map diff. It shows edges newly unlocked
or locked for each actor, fog cleared or added, and states that became unreachable. This is
often the fastest way for a domain expert to see what a change *means*.

### 4. Toprope's own map
In M1, the self domain declares Toprope's components and authoring workflow. Its generated
world map replaces the hand-drawn component diagram in the README. Until then, the README
diagram is a hand-drawn placeholder and is labeled as one.

## Consequences
- M0a emits `world-map.json` and the `world_map` / `how_to_reach` MCP tools. These are cheap,
  because everything is already derived.
- M0b adds the skill-tree view to the shell, and the map diff to impact reports.
- M1 produces Toprope's own map.
- The world map is a view. It never adds rules: every edge comes from the declaration.
