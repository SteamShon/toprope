# The domain model: objects, links and actions

Link: ① ② ④. This is the conceptual core of a Toprope domain. [`domain-schema.md`](domain-schema.md)
defines the syntax, and [`semantics.md`](semantics.md) the exact order of evaluation. This
page explains what the parts *are*, how they relate, and what each one drives. Read it first.

## The picture in one paragraph
**Objects** and **links** are the shape of the world: the things a workflow tracks and how
they relate. **Actions** are the only way that shape changes. **Preconditions** and
**invariants** set the limits a change must respect. The **transition matrix** says, for
each stage a tracked thing can be in, which actions are allowed and where they lead.
Today's state is the result of every action so far, replayed from the event log.

```
          ┌──────────── rules: preconditions, invariants ────────────┐
          │                                                          │
 role ──► action ──► (matrix cell for the target's stage) ──► effects ──► event
                              │                                  │
                         object ◄──── link ────► object     new state
```

## Objects: the things the work tracks
- An object type has **properties**: its facts, such as a name, an approver or a date.
- An object that moves through stages has one **stage field**, such as `status` with
  `draft → approved → running`. This is the state the transition matrix talks about. The
  object's other properties are state too, in the wider sense.
- An object exists only because an action created it, or because it was seeded as an example
  (a fixture).

## Links: how things relate, without anyone doing anything
- A link is a fact that holds between two objects: "this answer is to that question",
  "this experiment has that primary metric". It is a **relation**, not an event. Nobody
  "does" a link.
- **Name a link as a noun, seen from the object it starts at** (`Answer.question`,
  `Experiment.primary_metric`). Expressions read it like a field: `target.question.stage`.
- A link has a direction (`from`, `to`), a cardinality (one-to-one, many-to-one, and so on),
  and whether it is required. The value is stored on the `from` object as the id it points
  to. So **making or changing a link is an action setting that value.** The link adds the
  meaning: this value names an object of that type, with these rules.
- Do not store what can be computed. For example, which elements a declaration element
  references is derived from the declaration by the compiler. It is not a stored link,
  because a stored copy can drift from the truth.

## Actions: the only way anything changes
An action is something a role does, at one moment, that changes the world. Every change
goes through one, by a person, an agent on a person's behalf, or the system. The one
exception is seeding example data. Each action is recorded as an event.

An action connects to more than it seems:

| An action has… | Declared as | What it decides |
|---|---|---|
| who may do it | `actor`: roles, relation rules (`where`), `requires: human` | who is allowed; agents act only on a person's behalf, with a grant |
| what it acts on | `target` (an existing object) or `creates` (a new one) | which object's stage and rules apply |
| its inputs | `params` (typed; a param can name a linked object) | what the caller must supply, checked before anything runs |
| what must be true first | `preconditions` (`check` expressions over the target and its links) | refusals with a named reason, for rules that are not about the stage |
| what it is allowed to do in each stage | **one column of the transition matrix** | allowed (and the next stage), denied with a reason, not applicable, or undecided |
| what it changes | the next stage (from the matrix), then `set` effects | the new state, including link values |
| what it starts elsewhere | `call` effects to kernel services, `handoffs` to another domain | work that runs after the change is recorded, with a reply or a handoff |
| what it leaves behind | its event (`event`), and `records_decision` for decisions | the history: who, when, inputs, and for decisions, the rationale |

There are three kinds of change: **create** an object (`creates`), **move** its stage (the
matrix), and **set** facts (`set` effects, which also set link values). Creating a different
object from an effect is not in schema v1 (ADR-0021).

## The transition matrix: actions × stages
For each object with stages, the matrix has a row per stage and a column per action that
targets the object. Each cell answers: "in this stage, may this action happen, and where
does it lead?"

The example from [`domain-schema.md`](domain-schema.md):

| Experiment stage | `approve_experiment` | `launch_experiment` |
|---|---|---|
| `draft` | → `approved` | `{deny: "Launch requires approval."}` |
| `approved` | `{deny: "This experiment is already approved."}` | → `running` |
| `running` | `{deny: "Only drafted experiments can be approved."}` | `n/a` |
| `ended` | `n/a` | `undecided` (asked in the interview: can an ended experiment be relaunched?) |

- A cell is a next stage, `{deny: reason}`, `n/a` (never shown, never asked about),
  `undecided` (denied, and listed in every change report), or a per-role cell (`by_role`).
- A missing cell is `undecided`. **No cell is ever silently allowed.**
- The matrix is the single source for stage-based rules. Rules that are not about the stage
  are preconditions.

## Rules sit over the picture
- **Preconditions** belong to one action: "to launch, a primary metric must be set".
- **Invariants** belong to the world: "a running experiment always has an approver",
  however it got there. They are checked after every step of every generated test. At
  runtime a guard refuses a change that would break one, which means the declaration
  contradicts itself.

## The current state comes from the history
Every action that succeeds appends an event. An object's current state is those events
applied in order (event sourcing). So past behavior can be re-checked against a new
declaration: "with this change, 12 past actions would have been blocked" (log replay).

## What each part drives

| Part | Generated or checked from it | A change to it… |
|---|---|---|
| Object, property | event schemas, projections, MCP read tools and UI fields | removing or renaming one breaks what reads it: a major interface bump |
| Link | traversal in expressions, navigation in MCP and UI, world map, dependency analysis | the same: rules and screens that follow it break at compile time |
| Action | an MCP tool, an event, a harness test per (stage, role) | changes who can do what; log replay re-decides its past uses |
| Matrix cell | cell tests, the world map, `allowed_actions` | reruns only the tests of that cell (incremental) |
| Precondition | boundary tests, the reasons people see | can block past actions: log replay reports them |
| Invariant | checks after every test step, the runtime guard | can expose transitions the matrix allows but the world forbids |

## For one domain
For a particular domain, the same picture is generated from its declaration as
`domain-guide.md`, next to the world map, at every preview ([`world-map.md`](world-map.md)).

## In the interview
The staged interview builds a domain in this order (ADR-0025): purpose, then **people and
things** (roles, objects, links), then **actions**, then **transitions** (the matrix), then
invariants, examples and scenarios, handoffs, and review. Each stage needs the ones before
it, the way this page builds its picture.
