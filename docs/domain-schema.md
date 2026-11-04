# Domain schema v0 (draft)

Link: ① ② ③. The minimal core is **Object, Link, Action**, plus **`representation`**
(ADR-0008). Further concepts (policy, contract, flow) are added only when a milestone shows a concrete need, each with an ADR
naming that need.

```yaml
domain: example
version: 1
owner: SteamShon
glossary:                   # shared terms reused in MCP descriptions, UI labels, denial reasons
  readout: "The first analysis of an experiment's metrics after its planned duration."
roles: [pm, analyst, approver]

objects:
  Experiment:
    description: A controlled test of one hypothesis.
    properties:
      status: {enum: [draft, approved, running, ended, decided]}
      planned_days: {type: integer}
    source: {kind: system, ref: "src/models/Experiment.ts"}
    status: confirmed

links:
  tests: {from: Experiment, to: Hypothesis, cardinality: many-to-one, required: true,
          source: {kind: record, ref: "docs/experiments.md", quote: "Every experiment tests one hypothesis."},
          status: proposed}

actions:
  approve_experiment:
    description: Approve a drafted experiment for launch.
    actor: [approver]
    target: Experiment
    preconditions:
      - id: is-draft
        check: target.status == 'draft'
        reason: Only drafted experiments can be approved.
        source: {kind: interview, ref: "interview/2026-11-20#q7"}
        status: confirmed
    effects:
      - set: {target.status: approved, target.approved_by: actor.id}
    records_decision: true  # produces a Decision with who, when, inputs and rationale

representation:             # how the domain is shown to people (ADR-0008); never redefines meaning
  Experiment:
    list:   {columns: [name, status, primary_metric], group_by: status, sort: -started_at}
    detail:
      sections:
        - {title: Design, fields: [hypothesis, primary_metric, guardrails, planned_days]}
        - {title: Result, fields: [readout]}
      actions: [approve_experiment, launch_experiment, decide]   # shown only when allowed in the current state
    board:  {by: status}
  approve_experiment:
    form:   {fields: [note], confirm: "Approve this experiment for launch?"}
```

## Rules

- `representation` declares views per object (`list`, `detail`, `board`, …) and forms per
  action. Declared views compile deterministically to A2UI. Undeclared ones get schema
  defaults. Ad-hoc screens are composed by an LLM from declared components and allowed
  actions only. Labels and reasons always come from the glossary, `description` and `reason`.
- Every element may carry `source` (`system` | `record` | `interview` | `use`, with a ref or
  quote) and `status` (`proposed` | `confirmed` | `unknown`). Agents write only `proposed`.
  Only humans confirm. Unknowns stay explicit instead of being guessed.
- `description`, `reason` and `glossary` are written once and reused by every surface.
- `check` uses a small expression language (paths, comparison, `count`, `exists`, `now`).
  Extending it requires an ADR.
- `records_decision: true` turns an action into an accumulated work decision (④).

## Open questions

- Should judgment preconditions ("is this hypothesis falsifiable?") be `review` checks
  routed to a role?
- How do model versions apply to in-flight objects?
- Should LinkML or JSON Schema be reused for objects, adding only actions on top? To be
  revisited after M0.
