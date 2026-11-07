# Domain schema v1

Link: ① ② ③ ④. **The complete declaration language** (ADR-0023). Every construct is defined
here, with its status. A construct marked *defined* has fixed syntax and meaning, but the
kernel rejects it with a clear "not implemented yet" error until its milestone. Machine-
readable schemas: [`schema/domain.v1.schema.json`](../schema/domain.v1.schema.json) and
[`schema/representation.v1.schema.json`](../schema/representation.v1.schema.json).

| Construct | Section | Status |
|---|---|---|
| `domain`, `version`, `owner`, `glossary`, `roles` | core | implemented (M0a) |
| `objects` (properties, provenance) | core | implemented (M0a) |
| `links` | core | implemented (M0a) |
| `actions`: actor rules (role, relation), `target`/`creates`, params, preconditions, `set` effects, `records_decision`, `event`, `applies_in`, `requires: human` | core | implemented (M0a) |
| `call` effects to kernel services, replies from `external:kernel` | [Kernel services](#kernel-services-adr-0028) | implemented (M0a, ADR-0028) |
| `transitions` (matrix cells: state, `deny`, `n/a`, `undecided`, `to`, `by_role`) | core | implemented (M0a) |
| `invariants` with `scope: aggregate` | core | implemented (M0a) |
| `world` (fixtures, actors), `scenarios` (`do`, `read` steps) | core, scenarios | implemented (M0a) |
| `purpose` (problem, success metric, announcement) | [Purpose](#purpose) | M0a (metadata only) |
| `handoffs` | [Handoffs](#handoffs) | implemented (M0a, ADR-0024) |
| composition files (`*.composition.yaml`: members and wiring) | [Handoffs](#handoffs) | implemented (M0a, ADR-0026) |
| `approvals` on actions | [Approvals](#approvals) | defined; M0b |
| `read` on objects and properties | [Read visibility](#read-visibility-adr-0042) | defined; M0b |
| `invariants` with `scope: cross` + `reservations` | [Reservations](#cross-aggregate-invariants-and-reservations) | defined; M0b |
| `timers`, scenario `advance` steps | [Timers](#timers) | defined; M0b |
| `functions` | [Functions](#functions) | defined; M0b |
| `external` sources and `external:<source>` actors | [External events](#external-events) | `external:kernel` and kernel-service effects in M0a (ADR-0028); other sources M0b |
| representation files and host overlays | [Representation](#representation-layer-adr-0008) | defined; M0b |
| `create` effects | — | **not in v1** (rejected, ADR-0021) |

The core is **Object, Link, Action**, plus a **transition matrix** and **invariants** per
stateful object (ADR-0010). What these are, and what each one drives, is explained in
[`domain-model.md`](domain-model.md): read it before this reference. How the domain is shown lives in a separate, separately compiled
**representation** layer (ADR-0008). Concepts not listed here (policy, execution contract,
flow orchestration) are added only by an ADR naming the need.

Do not confuse the deferred *execution contract* concept with the **domain interface**. The
domain interface is a compiler output that the representation layer and handoffs read
(ADR-0008).

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
                   status: confirmed}
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
    records_decision: true  # produces a Decision: who, when, the params, the prior state, a rationale
  launch_experiment:
    description: Start traffic to an approved experiment.
    actor: [eng]
    target: Experiment
    effects:
      - set: {target.started_at: "now()"}

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
- **Effect values** in `set` are check-language expressions: `actor.id`, `"now()"`,
  `params.note`. A string literal is quoted inside the expression: `"'manual'"`.
- **Param names** are identifiers (letters, digits, `_`), so expressions can read them as
  `params.<name>`. `target_id`, `new_id`, `idempotency_key`, `thread_id` and `run_id` are
  reserved: every action surface carries them.
- `check` uses a small expression language: paths, comparison, `in` / `not in`, `and` / `or` /
  `not`, list literals, `+` / `-` on numbers, `count`, `exists`, `now`. `+` also joins a
  string with a string or an integer (ADR-0024); floats, booleans, null and lists
  are refused. The set operators and boolean combinators were added by ADR-0010. Any further
  extension requires an ADR.
- `records_decision: true` turns an action into an accumulated work decision (⑤). Every such
  action takes an optional `rationale` (string), the reason the person gives. The declaration
  model adds it, so every surface offers it; it is stored in the `DecisionRecorded` event when
  given. A decision action may not declare it (`reserved-param`); a non-decision action may, but
  then cannot become a decision action without renaming it (ADR-0041).
- **Transition matrix** (ADR-0010):
  - It is the single source for state-based rules. Every (state, action) cell is one of:
    a target state, `{deny: reason}`, `n/a`, `undecided`, or a per-role cell
    `{by_role: {approver: approved, eng: {deny: "..."}}}` (roles not listed are `n/a`).
  - A cell missing from a declared row is `undecided`, and the validator warns about it.
  - `n/a` denies with the standard reason "not applicable when <state>". It is recorded and
    never shown as available, and it is not asked about in the interview.
  - `undecided` cells deny with the reason "undecided" and are listed in every change report.
    No cell is ever silently allowed.
  - An action is allowed only if its matrix cell allows it, the actor has the role, and every
    non-state precondition holds. At runtime, an **invariant guard** also checks the
    resulting state before the event is appended (ADR-0012). If the guard triggers, the
    declaration is inconsistent: its matrix allows a transition that its invariants forbid.
    It is not a normal denial.
- **Invariants** are checked after every step of every generated test, at every level. The
  model interpreter runs **without** the guard, so it reports the violation itself. Runtime
  levels run **with** it, so they report an `InvariantGuardTriggered` event at the same step.
  Parity treats the two as the same outcome, and either one fails the harness.
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
- **Replay parity**: replaying the events a test produced rebuilds the same projected state
  (ADR-0012).
- **Coverage report**: cells, invariants, views, flows, and unreachable states.

A failing cell test, an invariant violation or a parity failure blocks deployment of that
build. Only tests affected by a change are re-run. Every other test keeps its cached
result, keyed by the hashes of its inputs (ADR-0013). The interviewer turns `undecided` cells and candidate invariants into plain
questions for the expert, so the expert never has to see the matrix.

### Example scenarios (flows)

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

## Purpose

Why the domain exists. The interview opens with this (ADR-0014, ADR-0023). It is written in
the owner's words, with no technical terms. A 3–6 sentence "announcement" written *before*
the domain is built is the test: if it cannot be written, the domain is not understood yet.

```yaml
purpose:
  problem: "Experiments get approved and launched by word of mouth, so nobody can tell later why one shipped."
  success_metric: {name: "decisions with recorded rationale", direction: up,
                   definition: "share of ship/kill decisions with inputs and rationale on record"}
  announcement: >
    Experiments now go through one place. You can see who approved what, why, and on which
    readout. Launching without approval is no longer possible.
```

Metadata only: it is shown in the world map and the change report, and it is the first
interview topic. It never changes behavior.

## Handoffs

A typed request from this domain into another domain's **published interface** (ADR-0022).
The handoff names an action of the other domain, and maps its params from this domain's
state with expressions. The compiler checks the mapping against the other domain's interface,
so a major bump there breaks the handoff at compile time.

```yaml
handoffs:
  deliver_approved_version:
    when: {action: approve_version, outcome: ok}       # fires after this action succeeds
    to:   {domain: domain-delivery, interface: "1.x", action: request_delivery}
    params:
      domain_id: target.domain_id
      version: target.number
      environment: "'staging'"
      approver: actor.id
    target: "target.domain_id + ':' + target.number"   # id of the request in the receiving domain
```

How a handoff runs (docs/semantics.md step 12):
- It is sent from an **outbox after the sender's action is appended**. It never blocks or
  rolls back the sender's action.
- The command in the receiving domain names its `target` (an expression, as with `params`).
  Its actor is the `system` actor `handoff:<sender domain>.<name>` (ADR-0026), acting on behalf of the person who
  caused the sender's action (that person's principal, if an agent acted). Its idempotency
  key is `<handoff name>:<sender event id>`, so retries never deliver twice.
- The receiving action must allow `system` in its actor rule. It is then evaluated like any
  other command, with all the receiver's rules.
- The outcome is recorded in both stores, linked by the handoff id (ADR-0024: the
  receiver's events carry it as `causation`; the sender records `HandoffDelivered`,
  `HandoffDenied` or `HandoffFailed`). A denial becomes a
  `HandoffDenied` event in the sender's domain, which the sender's own rules and proposals
  can react to.

A system of domains is declared in a **composition file** (ADR-0026). Domains compose and
never inherit: they connect only through published interfaces.

```yaml
# self.composition.yaml
composition: toprope-self
version: 1
members:                       # key = the member's declared `domain` name
  domain-authoring: {declaration: authoring.domain.yaml, interface: 1}   # published major
  domain-delivery:  {declaration: delivery.domain.yaml,  interface: 1}
wiring:
  - {from: domain-authoring.deliver_approved_version, to: domain-delivery.request_delivery}
```

Compiling a composition checks:
- every member
- that every handoff is wired exactly as it declares
- each wire's contract against the receiver's published major

At runtime, a receiver accepts only the handoffs wired to each action. Any other handoff is
`denied: actor`. The composed world map joins the members at the wires, so path questions
cross domains.

## Approvals

An action may need several distinct approvers before it fires (ADR-0015).

```yaml
actions:
  ship_experiment:
    description: Ship the winning variant.
    actor: [approver]
    target: Experiment
    approvals: {count: 2, from_role: approver, distinct: true}
```

Each call records an `ApprovalRecorded` event and returns `pending` until the count is
reached. Then the transition fires as a normal command (docs/semantics.md step 7). Rules:
- An approval counts only if its caller passes the action's actor rule **and** holds
  `from_role`.
- `distinct` counts **people**. An agent's approval counts as its principal's, so one person
  cannot meet a two-person rule through agents.
- Approvals are bound to the target's version. Any change to the target resets them, and
  firing the action resets them too. An optional `within: {hours: 48}` expires them.

## Cross-aggregate invariants and reservations

An invariant across objects declares `scope: cross` and names the reservation that enforces
it (ADR-0015). A reservation is a small generated aggregate, keyed by an expression. An
object holds a claim for as long as it stays in the listed states.

```yaml
invariants:
  - id: one-running-per-surface
    on: Experiment
    scope: cross
    enforced_by: running-slot
    check: "true"       # the reservation enforces it; the check documents intent
    reason: At most one experiment runs on a surface at a time.

reservations:
  running-slot:
    on: Experiment
    key: target.surface
    while_in: [running]
    capacity: 1
```

Rules:
- In v1 a `cross` invariant **must** name `enforced_by`. The check language cannot range
  over other objects, so an "after the fact" cross check could not be written.
- `enforced_by` is only valid on `scope: cross`.
- `capacity` defaults to 1.
- If an effect changes the `key` of an object that holds a claim, the claim moves to the new
  key in the same saga. It is denied (`denied: reservation`) if the new key is full.

## Timers

A timer issues an action as the `system` actor when an object has been in a state for a
while (ADR-0015). The fired action must list `system` in its actor rule, or the timer is a
compile error. Deadlines are timers that fire a "deadline passed" action. The harness runs
on a virtual clock, and scenarios advance it explicitly.

```yaml
timers:
  end-after-planned-days:
    on: Experiment
    in_state: running
    after: {field: planned_days, unit: days}   # or a fixed {days: 14} / {hours: 6}
    do: end_experiment
```

Scenario step to move the virtual clock: `- {advance: {days: 15}}`.

## Functions

Typed, pure computations that do not belong in generated code, such as a sample size or a
statistical readout (ADR-0015). They are implemented outside the declaration (by a person
or an agent) and must pass their declared examples as contract tests. Checks and effects
call them by name.

```yaml
functions:
  sample_size:
    description: Users per variant for the minimum detectable effect.
    inputs: {baseline: {type: number}, mde: {type: number}}
    output: {type: integer}
    examples:
      - {in: {baseline: 0.1, mde: 0.02}, out: 3623}
```

Usage in a check: `"count(target.variants) * sample_size(target.baseline, target.mde) <= target.traffic"`.

Functions may be called in actor relations, preconditions, effects and invariants (steps
4–10), and while computing allowed actions for views. So they must be pure, deterministic
and fast. They may not read the store, the clock or the network: pass `now()` in as an input
if needed.

## Kernel services (ADR-0028)

An action may call a **kernel service**, and name the action that receives its result. This
is how a domain does real work without hand-written glue, so a regenerated domain still
works. The catalog is the kernel itself (ADR-0027):

| Service | Inputs | Result (besides `ok`, `error`) |
|---|---|---|
| `validate` | `declaration` | `errors`, `warnings`, `summary` |
| `compile` | `declaration` | `objects`, `actions`, `elements`, `summary` |
| `check_composition` | `composition` | `issues`, `summary` |
| `run_harness` | `declaration` | `findings`, `cells_covered`, `unreachable`, `summary` |
| `world_map` | `declaration` | `undecided`, `unreachable`, `edges` |
| `read_source` | `source` | `chunks`, `local_only` |
| `fetch_source` | `source` | `sha256` |
| `search_sources` | `query` | `refs` (redacted; local-only never served) |
| `stage_questions` | — | `stage`, `bundle`, `questions` (the current stage's bundle, ADR-0025) |
| `propose_element` | `path`, `value` (JSON), `source` | `issues`, `summary`: always `proposed`, citing a real chunk (ADR-0037) |
| `record_answer` | `question`, `answer`, `decisions` (JSON) | `ref`: the owner's words; decisions become proposed elements citing it |
| `confirm_element` | `paths` (or `all`), `approver` | `confirmed`: the calling person must be the approver |
| `skip_stage` | `stage`, `reason` | `skipped` |
| `commit` | `declaration`; optional `evidence` (strings: interview lines, events, check records the change rests on; ADR-0041) | `id`, `seq`, `content`, `created`, `parent`, `interface`, `to_review`, `last_approved` (ADR-0029) |
| `diff` | `domain`, `from`, `to` | `changed`, `added`, `removed`, `to_review` |
| `checkout` | `domain`, `commit`, `declaration` | `content` (loads a commit into a working copy, ADR-0032) |
| `change_check` | `domain`, `commit` | `passed`, `errors`, `warnings`, `failing`, `summary` (recorded on the commit, ADR-0009) |
| `approve_commit` | `domain`, `commit`, `approver` | `approved`, `main` (merges into `main` and tags it, ADR-0033) |
| `preview` | `domain`, `commit` | `build`, `harness_ok` |
| `deploy` | `domain`, `commit`, `approver` | `deployed` (under the fixed floor, ADR-0022, ADR-0029) |

`changed`, `added`, `removed` and `to_review` are lists of element keys: a reply param that
receives one is `{type: string, many: true}`. `approve_commit` and `deploy` record a person's
decision: the kernel refuses them unless the action that called them was taken by that person
(the `approver`), so no declaration can make an agent, the system or the kernel approve or
deploy.

```yaml
actions:
  check_version:
    description: Check a domain version.
    actor: [owner]
    target: DomainVersion
    effects:
      - call: run_harness
        with: {declaration: target.declaration}    # inputs: expressions on the resulting state
        reply: record_harness_result
  record_harness_result:
    description: Record the harness result of a version.
    actor: ["external:kernel"]                      # only the kernel replies
    target: DomainVersion
    params: {ok: {type: boolean}, findings: {type: integer}}
    effects:
      - set: {target.harness_ok: params.ok, target.findings: params.findings}
```

Rules:
- **The call.** It is appended with the action, as an `EffectRequested` outbox event, and
  runs after the append (`docs/semantics.md` step 12). A failure never blocks the action.
- **The reply.** It is a command from `external:kernel` to the `reply` action on the same
  object, keyed by the effect id, so it is applied at most once. It goes through the matrix,
  preconditions and invariants like any other command.
- **Every field, every time.** A result always has every field: `ok`, `error` (`""` when
  ok), and the service's fields, with defaults when it failed. A failed call (including
  inputs of the wrong type) still replies, so the declaration decides what a failure means,
  usually with a gate on a later action.
- **Compile-time checks.** The service exists; its inputs are all mapped and no others; the
  reply exists, targets the same object type and allows `external:kernel`; the reply's
  params are fields of the result, of the same type. An action is either for
  `external:kernel` or for others, never both.
- **A reply may create** the object a service names (ADR-0029): `commit` returns an `id`, and
  a reply with `creates:` makes the Commit with that id. It runs only on success. If the
  object exists already (the working copy was unchanged), nothing is created and that is not
  an error.
- **Testing.** In scenarios, the kernel's results are ordinary steps:
  `{actor: {external: kernel}, do: record_harness_result, target: V1, params: {ok: true, findings: 0}}`.

## External events

An inbound event (a webhook, for instance) is an action whose actor is an `external:<source>`
system actor (ADR-0015). It goes through the same matrix, preconditions and invariants.
The action's actor list holds only external actors, and the action must appear in that
source's `actions`. Mixing external and human actors in one action is a compile error:
declare two actions instead.

```yaml
external:
  flags:
    description: The feature-flag service.
    actions: [record_rollout_finished]

actions:
  record_rollout_finished:
    description: The flag service reports a rollout completed.
    actor: ["external:flags"]
    target: Experiment
```

## Actors and agents (runtime, not declared)

People, agents and system actors come from the `Identity` port (ADR-0016). Two actor names
are reserved and are not roles: `system` (timers, handoffs and fixtures) and
`external:<source>`. Actor rules may name them directly. Agents act
`on_behalf_of` a person with a **grant** (actions, targets, expiry), which is issued at
runtime, not in the declaration. The declaration controls agents with `requires: human` and
with actor rules: an agent must satisfy the rule both for itself and for its principal.
A check or an effect can read `actor.principal` (`id`, `kind`, `roles`, `role`): the person an
agent acts for, or the actor itself when it is not an agent. Record and compare
`actor.principal.id` to say "not the proposer, nor the proposer's agent" (ADR-0041).

## Read visibility (ADR-0042)

Who may *read* what, beside who may *do* what. Defined now so it is reviewed before any surface
depends on it; the kernel refuses it until M0b, when the query tools let agents read history.

```yaml
objects:
  Readout:
    description: Metric results of an experiment after its planned duration.
    read: [pm, analyst, approver]          # who may read a readout at all
    properties:
      primary_delta: {type: number}
      guardrail_regressed: {type: boolean, read: [analyst, approver]}   # and this field
```

- `read` on an object type lists the roles that may read its objects; on a property, the roles
  that may read that property. Without `read`, every role may read, as now.
- It applies to every surface that reads: the MCP read tools, the command line's `get` and
  `history`, the query tools and the guide's examples. An object an actor may not read is
  reported as not found (like an action whose existence is hidden, ADR-0021); a property it may
  not read is left out.
- An agent must satisfy it both for itself and for its principal, like an actor rule.
- It limits what is shown, never what is checked: the gate, invariants, the harness, `system`
  and `external:kernel` read everything.

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
- Should `create` effects (creating another object from an action) be added? They are
  rejected for now (ADR-0021).
- In-flight objects across model versions are handled by migration plans (ADR-0018). The
  plan syntax is defined with M0b.
