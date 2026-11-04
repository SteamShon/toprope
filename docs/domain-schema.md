# Domain schema v0 (draft)

Link: ① ② ③. The minimal core is **Object, Link, Action**. How the domain is shown lives
in a separate, separately compiled **representation** layer (ADR-0008, below). Further
concepts (policy, contract, flow) are added only when a milestone shows a concrete need,
each with an ADR naming that need.

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

```

## Rules

- Every element may carry `source` (`system` | `record` | `interview` | `use`, with a ref or
  quote) and `status` (`proposed` | `confirmed` | `unknown`). Agents write only `proposed`.
  Only humans confirm. Unknowns stay explicit instead of being guessed.
- `description`, `reason` and `glossary` are written once and reused by every surface.
- `check` uses a small expression language (paths, comparison, `count`, `exists`, `now`).
  Extending it requires an ADR.
- `records_decision: true` turns an action into an accumulated work decision (④).

## Representation layer (ADR-0008)

Representation lives in separate files and compiles against the **domain contract** (the
hashed list of objects, fields, actions and glossary produced by compiling the domain), not
the domain source. Layers resolve in order: schema defaults → base (domain author) → host
overlay.

```yaml
# experiment.representation.yaml  (base, written by the domain author)
representation: experiment-ui
version: 7
targets: {domain: example, contract: ">=1 <2"}   # validated on every domain change
views:
  Experiment:
    list:   {columns: [name, status, primary_metric], group_by: status, sort: -started_at}
    detail:
      sections:
        - {title: Design, fields: [hypothesis, primary_metric, guardrails, planned_days]}
        - {title: Result, fields: [readout]}
      actions: [approve_experiment, launch_experiment, decide]  # shown only when allowed now
    board:  {by: status}
forms:
  approve_experiment: {fields: [note], confirm: "Approve this experiment for launch?"}
```

```yaml
# acme.overlay.representation.yaml  (host overlay)
overlay: acme
extends: experiment-ui@7
components:                                  # host components registered in the renderer catalog
  AcmeMetricChart: {package: "@acme/toprope-ui", props_from: [Readout]}
aliases:                                     # host wording, mapped to glossary terms
  readout: "Result review"
views:
  Experiment:
    detail:
      sections:
        - {title: Result, component: AcmeMetricChart, fields: [readout]}
```

Rules:
- A representation may reference only what is in the contract. A broken reference fails
  the build when either layer changes.
- Host components get data and the currently allowed actions, and act only through
  Execution. They cannot add actions, rules or fields.
- Wording changes are declared as `aliases` of glossary terms. Silently replaced labels are
  build warnings.
- Declared views compile deterministically to A2UI. Undeclared views get schema defaults.
  Ad-hoc screens are composed by an LLM from the catalog and the allowed actions only.

## Open questions

- Should judgment preconditions ("is this hypothesis falsifiable?") be `review` checks
  routed to a role?
- How do model versions apply to in-flight objects?
- Should LinkML or JSON Schema be reused for objects, adding only actions on top? To be
  revisited after M0.
