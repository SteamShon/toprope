# ADR-0041: A domain keeps two graphs: the world model and the context graph

- Link: ① iterate safely, ② model is right, ⑤ evolves · Status: accepted · 2026-11-06 · decided
  by: SteamShon (the definition, from the researcher's notes, and the recommended answer to each
  open question; drafted by the assistant)
- Builds on: ADR-0004 (provenance and status), ADR-0011 (the world model), ADR-0012 (event
  sourcing), ADR-0016 (authorization), ADR-0029 and ADR-0033 (commits, approval by merge)
- Amends: ADR-0012 (what a decision record carries: Resolved 2), charter §5 ("No
  self-approval": its scope in M1, Resolved 4)

## Context
Toprope already keeps two different kinds of knowledge, but the documents do not name the
difference:

- what a domain **is and allows**: objects, links, actions, states, the transition matrix,
  invariants and preconditions, roles and actor rules. This is the "world model" of ADR-0011. It
  is compiled into the Execution gate, the generated tools and the harness, and it is enforced.
- what **explains and changes** it: the interview log, elements an agent proposed, the `source`
  on every element, decision events, commits, approvals and check records. None of this is
  enforced by itself.

The researcher's notes separate six kinds of knowledge that must not be mixed: an **observation**
(what happened), a **memory** (its record), an **interpretation or hypothesis** (what it may
mean), a **preference** (a tendency that depends on conditions), a **rule** (a condition accepted
as binding) and a **permission** (what one actor may do). They add that knowing a method, having
adopted something as a default, and approving one action are three different things, and that a
past choice does not by itself create a rule or a permission.

Without a name for the split, two mistakes are easy: treating a recorded observation or an
agent's hypothesis as if it were a rule, and treating a rule as if it needed no record of why it
exists.

## Decision
1. **Two graphs, as a classification.** Every piece of a domain is classified as **world model**
   or **context graph**. This is a classification, not a storage split: an element's `source` and
   `status` (context) sit inside the declared element (world model), and one declaration file
   holds both. The context graph is a view derived from existing records, not a new store.
   - The **world model** is what exists and what may happen: objects, links, actions, functions,
     states, and the **rules** and **permissions** declared over them (matrix cells, invariants,
     preconditions; roles, actor rules, `requires: human`). It is enforced: the gate, the
     generated tools and the harness come from it.
   - The **context graph** is why the world model is as it is and what happened under it:
     **observations**, **memory**, **interpretations and hypotheses**, **preferences**,
     **decisions** with their reasons, and the **sources and history** of every element,
     including open questions. It is not enforced. It explains, and it proposes.
2. **Only rules and permissions are enforced.** Of the six kinds, only rules and permissions are
   in the world model; the other four are in the context graph. Two things sit between them:
   - **Instances and current state** are derived from the event log (ADR-0012). They are what
     the gate and the invariant guard check, and they change only through allowed actions. The
     same events are the context graph's memory and observations.
   - An **`undecided` cell** is a world-model rule, because it refuses (fail-closed); the
     question it stands for is in the context graph until someone answers it.
3. **The one way across.** A declared rule or permission changes only through a reviewed change:
   a commit on the domain's protected `main` (ADR-0033, not the repository's git `main`), merged
   by `approve_commit`, which only a person may take and which requires the commit's checks to
   have passed. Recording an observation, adopting a default in conversation, or an agent
   proposing an element changes nothing that is enforced until such a commit is approved.
   Who holds a role, and which grants an agent has, are issued at runtime by the Identity port
   (ADR-0016) and are outside this rule (see Open 5).
4. **Policies.** An adopted policy is a rule in the world model. Its candidates, reasons and
   change history are in the context graph. "New creatives go to a test campaign first" is a
   hypothesis in the context graph while the team checks it against the numbers, and a rule in the
   world model once a commit that declares it is approved. An exception that the gate honours
   would be a permission with a scope and an expiry, and its reason context; exceptions are not
   modeled yet (Open 6).
5. **Today's parts are mapped, not changed.** Nothing in the declaration format or the stores
   changes with this ADR:

   | Kind | Graph | Where it is now |
   |---|---|---|
   | objects, links, actions, states | world model | the declaration |
   | functions | world model | function ports (ADR-0015), M0b |
   | rules | world model | matrix cells (including `undecided`, which refuses), invariants, preconditions |
   | permissions, declared | world model | roles, actor rules, `requires: human` |
   | permissions, at runtime | (outside the declaration) | role holders and grants from the Identity port (ADR-0016) |
   | instances and current state | derived; checked by the gate | projections of the event log |
   | observations, memory | context graph | domain events, refused attempts, effect outcomes; the interview log |
   | interpretations, hypotheses | context graph | elements with `status: proposed`, by provenance (Resolved 1) |
   | decisions | context graph | `DecisionRecorded` events: who, when, the action's params and the target's prior state |
   | evidence | context graph | `world` fixtures and `scenarios`, which the harness also runs as checks |
   | sources and history | context graph | `source` and `status` on elements; commits, approvals, check records |
   | open questions | context graph | the question behind each `undecided` cell; `status: unknown` |
   | preferences | context graph | not modeled |

## Consequences
- The README and `docs/how-it-works.md` use the two names, with this ADR as the definition.
- Reviewing a change means checking both graphs: what the world model will enforce (the change
  check, the harness) and why (the evidence the commit cites, Resolved 3).
- The proposal engine (M4) reads the context graph and writes only proposals. Accepting one is an
  approved commit, whichever surface it is accepted in.
- The query tools (M0b) cover the event store (ADR-0012). Joining commits, sources and the
  interview log into one queryable graph has no plan yet; until then the context graph is a set
  of records linked by element keys, commit ids and event streams (Resolved 3).

## Resolved (researcher, 2026-11-06: the recommendation in each case)
1. **Proposed elements.** Drafts and previews keep compiling and testing proposed elements, so a
   proposal can be tried. `approve_commit` refuses a commit that still holds any element with
   `status: proposed`: `check_commit` records how many there are, and approval requires none.
   Ignoring proposed elements in the gate was rejected, because a preview and a deploy would then
   behave differently without saying so.
2. **Decision records.** An action with `records_decision: true` takes an optional reserved
   parameter `rationale` (like `idempotency_key`), stored in its `DecisionRecorded` event. This is
   what ADR-0012's "with inputs and rationale" now means. An expected outcome and a re-review
   condition are decided in the M4 spec, by the proposal engine that reads them.
3. **Edges.** The context graph stays a derived view. Its edges today: an element to its source
   (`source`), a commit to the elements it changed (the semantic diff), a rule to the commit that
   adopted it (the element log), a decision to its action and target (the event). One edge is
   added: a commit may cite its evidence (interview lines, events, check records). An exception to
   the rule it bends waits for exceptions (6).
   *Note (2026-11-07, decided by the maintainer in the review of #124):* evidence is a typed pointer that must
   resolve, never a free string. A commit cites it after it is made, one citation at a time,
   through the kernel's `cite_evidence`: `interview`, `source`, `check`, `event` or
   `approval-run`, each with a strength (pointed, ran, observed, approved) and who cited it.
   The free-string `evidence` input of `commit` (#117, #118) is removed; the commit that used it
   keeps its record.
4. **Whose agent acted, and who approves.**
   - A check can read `actor.principal`: the principal's id and roles for an agent, the actor
     itself otherwise. Rules can then say "not the proposer, nor the proposer's agent".
   - Author ≠ approver is not required in the self domains during M1: ADR-0032 keeps one approver,
     and a local agent shares the researcher's git email (`docs/STATUS.md`, Open questions). A
     domain may declare it (`target.author != actor.principal`); it becomes the default when a
     domain has more than one owner (M2 or later).
   - In M1, charter §5's "No self-approval" means that an agent never approves (`requires:
     human`).
5. **Runtime permissions.** Role holders and grants stay with the Identity port (ADR-0016), not in
   the declaration: who holds a role changes for reasons that are not rule changes. Issuing a grant
   or changing a role is recorded as an event, so it is an observation in the context graph. In the
   self domains, `toprope.identity.yaml` is in git, so changing it already goes through a
   repository PR. *Refined (researcher, 2026-11-06):* Toprope does not issue grants or roles, it
   only sees them, so every event and refused attempt records the `permissions` it ran under (the
   actor's roles, the principal's, and the grant's actions, targets and expiry); a new grant or a
   changed role shows as a difference between events.
6. **Preferences and exceptions.**
   - Preferences are not a kind of their own: they are parameters with defaults, or proposed
     elements until someone confirms them. Revisit when a personal domain needs them.
   - An exception is a pattern, not a new construct: an action such as `grant_exception`
     (`requires: human`, `records_decision: true`) sets a flag on one target, and the rule reads
     `<rule> or target.exception_approved`. How many exceptions pile up on a rule is an input to
     the M4 proposals.

## Follow-up work
Each is its own PR, with tests:
- `check_commit` counts proposed elements; `approve_commit` requires none (Resolved 1)
- the reserved `rationale` parameter on decision actions (Resolved 2)
- an optional evidence field on commits (Resolved 3)
- `actor.principal` in checks, and `not-the-proposer` in `examples/paid-media/` using it (Resolved 4)
- events for issued grants and role changes (Resolved 5)
- the exception pattern in `examples/paid-media/` (Resolved 6)
