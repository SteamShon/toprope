# Domain schema v0 (draft)

Link: ① ② ④. The core is **Object, Link, Action**, plus a **transition matrix** and
**invariants** per stateful object (ADR-0010). How the domain is shown lives in a separate,
separately compiled **representation** layer (ADR-0008, below). Further concepts (policy,
execution contract, flow orchestration) are added only when a milestone shows a concrete
need, each with an ADR naming that need.

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
      approved_by: {type: string, optional: true}
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
    preconditions:          # only conditions that do NOT depend on state; state lives in the matrix
      - id: has-guardrails
        check: count(target.guardrails) >= 1
        reason: An experiment needs at least one guardrail metric before approval.
    effects:
      - set: {target.approved_by: actor.id}
    records_decision: true  # produces a Decision with who, when, inputs and rationale
  launch_experiment:
    description: Start traffic to an approved experiment.
    actor: [eng]
    target: Experiment
    effects:
      - set: {target.started_at: now}

transitions:                # state × action → target state | deny(reason) | n/a | undecided
  Experiment:
    field: status
    initial: draft
    matrix:
      draft:
        approve_experiment: approved
        launch_experiment: {deny: "Launch requires approval."}
      approved:
        approve_experiment: {deny: "This experiment is already approved."}
        launch_experiment: running
      running:
        approve_experiment: {deny: "Only drafted experiments can be approved.",
                             source: {kind: interview, ref: "interview/2026-11-20#q7"}, status: confirmed}
        launch_experiment: n/a
      ended:                # reached by actions omitted from this example
        approve_experiment: n/a
        launch_experiment: undecided      # "can an ended experiment be relaunched?" → asked in the interview
      decided:
        approve_experiment: n/a
        launch_experiment: n/a

invariants:                 # must hold in every reachable state, after every step
  - id: running-has-approver
    on: Experiment
    check: target.status not in ['running', 'ended', 'decided'] or exists(target.approved_by)
    reason: Nothing runs without someone having approved it.
    source: {kind: interview, ref: "interview/2026-11-20#q9"}
    status: confirmed
  - id: running-has-start
    on: Experiment
    check: target.status not in ['running', 'ended', 'decided'] or exists(target.started_at)
    reason: A launched experiment records when it started.

world:                      # the expert's examples; the compiler grows a small world from them
  fixtures:
    - Hypothesis: {id: H1, statement: "A shorter signup raises activation."}
    - Metric: {id: M-activation, name: activation_rate}
    - Metric: {id: M-latency, name: p95_latency}
    - Experiment: {id: E-onboarding, name: "New onboarding", status: draft, planned_days: 14,
                   hypothesis: H1, primary_metric: M-activation, guardrails: [M-latency]}
    - Experiment: {id: E-bare, name: "No guardrails yet", status: draft, planned_days: 7,
                   hypothesis: H1, primary_metric: M-activation, guardrails: []}   # boundary for has-guardrails
  actors: {approver: [ana], eng: [eli], pm: [pat], analyst: [ann]}
```

## Rules

- Every element may carry `source` (`system` | `record` | `interview` | `use`, with a ref or
  quote) and `status` (`proposed` | `confirmed` | `unknown`). Agents write only `proposed`.
  Only humans confirm. Unknowns stay explicit instead of being guessed.
- `description`, `reason` and `glossary` are written once and reused by every surface.
- `check` uses a small expression language (paths, comparison, `in`, `count`, `exists`,
  `now`). Extending it requires an ADR.
- `records_decision: true` turns an action into an accumulated work decision (⑤).
- **Transition matrix** (ADR-0010):
  - It is the single source for state-based rules. Every (state, action) cell is one of:
    a target state (optionally per role), `{deny: reason}`, `n/a`, or `undecided`.
  - `undecided` cells deny with the reason "undecided" and are listed in every change report.
    No cell is ever silently allowed.
  - An action is allowed only if its matrix cell allows it, the actor has the role, and every
    non-state precondition holds.
- **Invariants** are checked after every step of every generated test, at every level.
- **World**: fixtures are the expert's realistic examples, not test data written for the
  harness. The compiler grows them into a small world: at least one instance per reachable
  state, every role as an actor, and boundary values for each non-state precondition. It
  reports unreachable states.

## Generated harness (ADR-0009, ADR-0010)

From the matrix, invariants, world and flows, the compiler generates a harness that runs at
every level: the model interpreter, Execution, an MCP client against the generated server,
compiled A2UI views, and adapters.

- **Cell tests**: every (state, action, role) cell is tried from a small-world instance in
  that state.
- **Invariant checks**: after every step.
- **Bounded exploration**: stateful property-based search over action sequences (first
  adapter: Hypothesis). A counterexample is reported as a minimal flow in domain terms.
- **Example flows**: run as written.
- **Parity**: the same test must give the same outcome on every surface.
- **Coverage report**: cells, invariants, views, flows, and unreachable states.

A failing cell test, an invariant violation or a parity failure blocks deployment of that
build. The interviewer turns `undecided` cells and candidate invariants into plain
questions for the expert, so the expert never has to see the matrix.

### Example flows

Flows are the expert's short stories: a starting state, then `do` (action) and `read`
(view) steps with expectations.

```yaml
scenarios:
  - id: no-approve-running
    given: {Experiment: {id: E1, status: running, approved_by: ana, started_at: "2026-11-01"}}
    steps:
      - {actor: {role: approver}, do: approve_experiment, target: E1,
         expect: {denied_by: matrix, reason_shown: true}}

  - id: draft-to-running
    given: {from_world: E-onboarding}
    steps:
      - {actor: {role: pm}, read: {view: Experiment.detail, target: E-onboarding},
         expect: {actions_shown: [], fields_include: [hypothesis, primary_metric]}}   # pm sees no actions
      - {actor: {role: eng}, do: launch_experiment, target: E-onboarding,
         expect: {denied_by: matrix}}
      - {actor: {role: approver}, do: approve_experiment, target: E-onboarding, params: {note: "ok"},
         expect: {state: {E-onboarding.status: approved}, decision_recorded: true}}
      - {actor: {role: eng}, read: {view: Experiment.detail, target: E-onboarding},
         expect: {actions_shown: [launch_experiment]}}
      - {actor: {role: eng}, do: launch_experiment, target: E-onboarding,
         expect: {state: {E-onboarding.status: running}}}

  - id: no-approve-without-guardrails
    given: {from_world: E-bare}
    steps:
      - {actor: {role: approver}, do: approve_experiment, target: E-bare,
         expect: {denied_by: has-guardrails}}
```

`do` steps run as action calls at the Execution and MCP levels, and as form submissions at
the UI level. `read` steps check what a declared view shows in that state, for that actor.

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
