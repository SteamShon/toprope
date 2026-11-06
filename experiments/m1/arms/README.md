# M1 Phase B: the three arms' materials

Link: ① iterate safely, ⑥ (pilot, ADR-0034). How they are used: [ADR-0040](../../../docs/adr/0040-m1-phase-b-execution-protocol.md).

Every arm starts from the same approved self-domain commits, `authoring@4-b0c8834e25d9bbc7` and
`delivery@1-584aaeea5e686ee8` (each commit store's `main`; the binding names the same).

| Directory | Arm | Made by |
|---|---|---|
| `structured/` | structured spec | `python -m phase_b materials`: the two declarations as approved, and the composition with its handoff, given to the arm as text |
| `toprope/` | Toprope | the same command: a sandbox (the approved self domains as fixed tools, the declarations to change, their commit stores, two callers: the researcher's stand-in and an editor that only proposes) |
| `nl/` | natural-language skill | `python -m phase_b render`: `SKILL.md` and `EXAMPLES.md`, written from `structured/` alone by a fresh conversation that had only those files and file tools confined to them. Its transcript is `nl.render.jsonl` |

The run's manifest records each arm's materials hash. Change nothing here after the dry run
starts: a run refuses to resume with other materials.

## The researcher's review (the design's "second reader")

Read `nl/SKILL.md` and `nl/EXAMPLES.md` side by side with `structured/`. Check that every rule
in the declarations appears in the skill: who may take each action, what it needs first, what
it changes, which actions only a person may take, the states and what each refuses, the
invariants, the handoff, and the glossary. Also check that the skill adds no rule of its own.

Before this review, two blind checks ran (fresh agents that read only the declarations and the
skill; the assistant that wrote the harness has seen the key, so it did not judge the skill
itself):

- The first rendering left out the kernel services, the parameter types and the invariants'
  reasons, mixed transition-table denials into the preconditions, and said a person must
  preview. The render prompt was made stricter and the skill rendered again (no hand edits).
- The second found no missing or wrong rule. Left, as presentation only: the roles lines name
  `external:kernel` and `system` as actors; two notation notes; the `approve_commit` effects
  cell opens with the action's description; the links table says "Required: no" where the YAML
  is silent.

If the skill is wrong, delete `nl/` and render it again; do not edit it by hand (the arm's text
must come from the declarations, not from someone who knows the key).
