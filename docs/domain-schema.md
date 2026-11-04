# Domain schema v0 (draft)

Minimal core: **Object, Link, Action**. Policy, Contract and Flow from earlier Toprope
designs are left out until a concrete need appears. Each later addition gets an ADR
stating which task required it (ADR-0010).

Full example: [`examples/domains/experiment-lifecycle.domain.yaml`](../examples/domains/experiment-lifecycle.domain.yaml).

## Shape

```yaml
domain: experiment-lifecycle
version: 1
owner: SteamShon
glossary:                 # the shared language; terms reused in MCP descriptions and UI labels
  readout: "The first analysis of an experiment's metrics after its planned duration."

roles: [pm, analyst, approver, eng]

objects:
  Experiment:
    description: A controlled test of one hypothesis.
    properties:
      status: {enum: [draft, approved, running, ended, decided]}
      planned_days: {type: integer, min: 7}
    states: {field: status}            # optional: marks a lifecycle field

links:
  tests:     {from: Experiment, to: Hypothesis, cardinality: many-to-one, required: true}

actions:
  approve_experiment:
    description: Approve a drafted experiment for launch.
    actor: [approver]
    target: Experiment
    params: {note: {type: string}}
    preconditions:                     # each has an id and a human reason; returned on denial
      - id: is-draft
        check: target.status == 'draft'
        reason: Only drafted experiments can be approved.
      - id: has-guardrails
        check: count(target.guardrails) >= 1
        reason: An experiment needs at least one guardrail metric before approval.
    effects:
      - set: {target.status: approved, target.approved_by: actor.id}
    records_decision: true             # writes a Decision object with inputs and rationale
```

## Design rules

- Every element (object, property, link, action, precondition) may carry `source`
  (system | record | interview | use, with a reference or quote) and `status`
  (proposed | confirmed | unknown). Agents can only write `proposed`. Only humans confirm.
  Unknowns are kept explicit instead of guessed.
- `description`, `reason` and `glossary` are **the** text used in the MCP tool descriptions,
  the UI labels and the denial messages. They are written once.
- `check` uses a small expression language (path access, comparison, `count`, `exists`,
  `now`). If it becomes insufficient, that is an ADR, not a quiet extension.
- `records_decision: true` makes the action produce a structured Decision (who, when,
  inputs, rationale). Accumulation (M3) depends on this.

## Open questions

- Should preconditions that need judgment (e.g. "the hypothesis is falsifiable") be
  allowed as `review` checks, routed to a role instead of evaluated?
- How do model versions apply to in-flight objects? (Proposal: an object keeps the version
  it started under, unless a migration is approved.)
- Is it worth reusing LinkML or JSON Schema for objects, adding only actions on top? This
  will be revisited after M0.
