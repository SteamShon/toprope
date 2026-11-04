# Domain schema v0 (draft)

Link: ① ② ③. The minimal core is **Object, Link, Action**. How the domain is shown lives
in a separate, separately compiled **representation** layer (ADR-0008, below). Further
concepts (policy, execution contract, flow) are added only when a milestone shows a
concrete need, each with an ADR naming that need.

Do not confuse the deferred *execution contract* concept with the **domain interface**. The
domain interface is a compiler output that the representation layer reads (ADR-0008).

```yaml
domain: example
version: 1
owner: SteamShon
glossary:                   # shared terms reused in MCP descriptions, UI labels, denial reasons
  readout: "The first analysis of an experiment's metrics after its planned duration."
roles: [pm, analyst, approver, eng]

objects:
  Hypothesis:
    properties:
      statement: {type: string}
  Metric:
    properties:
      name: {type: string}
  Experiment:
    description: A controlled test of one hypothesis.
    properties:
      name: {type: string}
      status: {enum: [draft, approved, running, ended, decided]}
      planned_days: {type: integer}
      started_at: {type: datetime, optional: true}
    source: {kind: system, ref: "src/models/Experiment.ts"}
    status: confirmed
  Readout:
    description: Metric results of an experiment after its planned duration.
    properties:
      primary_delta: {type: number}
      guardrail_regressed: {type: boolean}

links:                      # a link is navigable from its `from` object by its name
  hypothesis:     {from: Experiment, to: Hypothesis, cardinality: many-to-one, required: true,
                   source: {kind: record, ref: "docs/experiments.md", quote: "Every experiment tests one hypothesis."},
                   status: proposed}
  primary_metric: {from: Experiment, to: Metric, cardinality: many-to-one, required: true}
  guardrails:     {from: Experiment, to: Metric, cardinality: many-to-many}
  readout:        {from: Experiment, to: Readout, cardinality: one-to-one}

actions:
  approve_experiment:
    description: Approve a drafted experiment for launch.
    actor: [approver]
    target: Experiment
    params:
      note: {type: string, optional: true}
    preconditions:
      - id: is-draft
        check: target.status == 'draft'
        reason: Only drafted experiments can be approved.
        source: {kind: interview, ref: "interview/2026-11-20#q7"}
        status: confirmed
    effects:
      - set: {target.status: approved, target.approved_by: actor.id}
    records_decision: true  # produces a Decision with who, when, inputs and rationale
  launch_experiment:
    description: Start traffic to an approved experiment.
    actor: [eng]
    target: Experiment
    preconditions:
      - id: is-approved
        check: target.status == 'approved'
        reason: Launch requires approval.
    effects:
      - set: {target.status: running, target.started_at: now}
```

## Rules

- Every element may carry `source` (`system` | `record` | `interview` | `use`, with a ref or
  quote) and `status` (`proposed` | `confirmed` | `unknown`). Agents write only `proposed`.
  Only humans confirm. Unknowns stay explicit instead of being guessed.
- `description`, `reason` and `glossary` are written once and reused by every surface.
- `check` uses a small expression language (paths, comparison, `count`, `exists`, `now`).
  Extending it requires an ADR.
- `records_decision: true` turns an action into an accumulated work decision (④).

## Scenarios (ADR-0009)

Domains carry their own tests. The change-check pipeline re-runs them on every edit, and a
changed outcome is a regression to confirm or fix.

```yaml
scenarios:
  - id: no-approve-running
    given: {Experiment: {id: E1, status: running}}
    when:  {action: approve_experiment, actor: {role: approver}, target: E1}
    expect: {denied_by: is-draft}
  - id: approve-draft
    given: {Experiment: {id: E2, status: draft}}
    when:  {action: approve_experiment, actor: {role: approver}, target: E2}
    expect: {state: {E2.status: approved}, decision_recorded: true}
```

Scenarios used as an experiment's held-out gold set are kept outside the domain, so they
cannot be edited by the loop they evaluate.

## Representation layer (ADR-0008)

Representation lives in separate files. It compiles against the **domain interface**, not
the domain source. The domain interface is the list of objects, fields, links, actions,
params and glossary terms produced by compiling the domain.

**Interface versioning.** The compiler derives the interface version from the diff of
each domain change:
- removing or renaming an element is **major**
- adding an element is **minor**
- changing only text (description, reason, glossary wording) is **patch**.

Each element also has its own content hash. Representations target a major range. A view
is rebuilt only when an element it references changed hash, and unaffected views are
reused.

Layers resolve in order: schema defaults → base (domain author) → host overlay.

```yaml
# experiment.representation.yaml  (base, written by the domain author)
representation: experiment-ui
version: 7
targets: {domain: example, interface: "1.x"}     # re-validated on every domain change
views:
  Experiment:
    list:   {columns: [name, status, primary_metric], group_by: status, sort: -started_at}
    detail:
      sections:
        - {title: Design, fields: [hypothesis, primary_metric, guardrails, planned_days]}
        - {title: Result, fields: [readout]}
      actions: [approve_experiment, launch_experiment]  # shown only when allowed now
    board:  {by: status}
forms:
  approve_experiment: {fields: [note], confirm: "Approve this experiment for launch?"}
```

```yaml
# acme.overlay.representation.yaml  (host overlay)
overlay: acme
extends: {representation: experiment-ui, version: "7.x"}   # base versions this overlay accepts
targets: {domain: example, interface: "1.x"}             # re-validated like the base
components:                                  # host components registered in the renderer catalog
  AcmeMetricChart: {package: "@acme/toprope-ui", props_from: [Readout]}
aliases:                                     # host wording, mapped to glossary terms
  readout: "Result review"
views:
  Experiment:
    detail:
      sections:
        - {title: Result, component: AcmeMetricChart, fields: [readout]}   # merged by title
```

Rules:
- A representation, base or overlay, may reference only what is in the domain interface.
  A broken reference fails the build when the domain, the base or the overlay changes.
- **Merge semantics.** Maps merge key by key. Keyed lists merge by key: `sections` by
  `title`, `columns` and `fields` by name, `actions` by name. An overlay entry with a
  matching key replaces that entry, and new keys are appended. To replace a whole list,
  write `{replace: [...]}`. In the example above, the overlay replaces only the *Result*
  section, and *Design* is kept.
- An overlay names the base versions it accepts. A base change outside that range, or one
  that breaks the overlay's references, fails the overlay's build. It never renders stale
  views.
- Host components receive data, labels (with aliases applied) and the currently allowed
  actions through the domain interface. They act only through Execution, and cannot add
  actions, rules or fields.
- Wording changes are declared as `aliases` of glossary terms. The compiler cannot inspect
  inside host components, so text hardcoded in a component is the host's responsibility and
  is **not** checked (ADR-0008).
- Declared views compile deterministically to A2UI. Undeclared views get schema defaults.
  Ad-hoc screens are composed by an LLM from the catalog and the allowed actions only.

## Open questions

- Should judgment preconditions ("is this hypothesis falsifiable?") be `review` checks
  routed to a role?
- How do model versions apply to in-flight objects?
- Should LinkML or JSON Schema be reused for objects, adding only actions on top? To be
  revisited after M0.
