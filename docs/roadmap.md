# Roadmap

Budget: ~10h+/week. Each milestone has a question, an exit criterion and a kill/pivot
criterion. Dates are targets, not commitments.

| | Question | Target |
|---|---|---|
| M0 | Can a minimal domain model compile into a working MCP surface with a state store and an event log? | 1–2 weeks |
| M1 | **H-Shared**: do agents make fewer meaning errors through the capsule? | 3 weeks |
| M2 | **H-Factory**: generated UI plus the author loop. What do the first build and later changes cost? | 3 weeks |
| M3 | **H-Accumulate**: log → proposal → decision → next version | 3 weeks |
| M4 | **H-Handoff**: second domain (code → product delivery), cross-domain handoff, write-up, go public | 3 weeks |

---

## M0: Domain core and compiler skeleton (1–2 weeks)

- Decide the implementation language and record an ADR. Trade-off: TypeScript suits MCP and
  UI generation, Python suits experiment analysis. The proposal is TypeScript for the
  core and generators, plus Python notebooks for analysis.
- Domain schema v0 (`docs/domain-schema.md`): Object, Link, Action (params, preconditions,
  effects, roles). Validate with JSON Schema.
- `examples/domains/experiment-lifecycle.domain.yaml` v0.
- Compiler v0: domain → MCP server. One tool per action, with descriptions generated from
  the model and preconditions checked at call time. Also read tools for objects and links.
- State store (SQLite) with a synthetic data generator for experiments and metrics.
- Event log (append-only JSONL): every action call, its verdict, its effect.

Exit: an agent (Claude Code or headless) runs the experiment lifecycle end to end through
the generated MCP against synthetic state, and every step is in the event log.

## M1: Shared-language experiment (3 weeks)

See [`experiments/M1-shared-language.md`](experiments/M1-shared-language.md). Three conditions:
docs plus generic tools / hand-written typed tools with prose rules / capsule-generated
MCP. About 12 scenario tasks, with a pilot gate, a cost estimate and a revision probe.

Exit: verdict on H-Shared with numbers.

Kill/pivot:
- If docs ≈ capsule, the agent-side value of the model is weak. Move the weight to the
  human side and accumulation (M2/M3).
- If hand-written typed tools ≈ capsule, the gain is vocabulary. The compiler's value is
  then cost (H-Factory), not accuracy.

## M2: Generated UI and the factory loop (3 weeks)

- Generate a human UI from the same capsule: object lists and details, links, and action
  forms with the same preconditions and role checks. Start schema-driven. Generative-UI
  specs are candidates.
- The author (the researcher) runs the loop: model → generate → use via UI and agent → fix.
- Measure: time to the first usable domain, time and lines changed for the 2nd and 3rd
  changes (e.g. add a guardrail rule, add an approval role), and how often the author had
  to touch generated code (target: never).
- Check that the UI and MCP always agree: same actions, same preconditions, same terms.

Exit: verdict on H-Factory. Kill: if changes need hand edits to generated surfaces, fix the
generator before moving on, or narrow what is generated.

## M3: Decision accumulation (3 weeks)

- Proposal engine: read event logs (blocked calls, repeated clarifications, exceptions,
  human overrides) and propose model diffs (new precondition, changed role, new state)
  with evidence links.
- Review in the UI: accept / edit / reject / scope / unsure. An accepted diff creates a new
  model version and regenerates the surfaces. Every decision is recorded with its inputs.
- Exceptions: "this once, with reason" is recorded. Accumulated exceptions become amendment
  proposals.
- Measure: proposal acceptance rate, clarifications and errors in later runs before and
  after accepted changes, and over-generalization incidents.

Exit: verdict on H-Accumulate.

## M4: Second domain, handoff, release (3 weeks)

- Model code → product delivery (PR → release → flag → rollout → verification) with the same
  core and compiler. No core changes should be needed. Record any that are.
- A typed handoff "experiment decided ship → delivery request" compared with a written note.
- Write-up: findings, negative results, claims we cannot make.
- Decide the license (Apache-2.0 proposed) and make the repository public (ADR-0005).

## Later (not planned)

- Thread C: learning from the accumulated decision log.
- Self-compile: model the domain-authoring workflow itself in Toprope.
- External effects: adapters to real systems with read-back and `UNKNOWN`.
- Harness² comparison: automatic propose–probe–compose vs. human-decided model changes.
- Durable runtime and host adapters.
