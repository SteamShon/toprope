# ADR-0041: A domain keeps two graphs: the world model and the context graph

- Link: ② model is right, ⑤ evolves · Status: **proposed** · 2026-11-06 · decided by: (pending)
  SteamShon (definition from the researcher's notes; drafted by the assistant)
- Builds on: ADR-0004 (provenance and status), ADR-0011 (the world model), ADR-0012 (event
  sourcing), ADR-0016 (authorization), ADR-0029 and ADR-0033 (commits, approval by merge)

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
   holds both.
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
   | interpretations, hypotheses | context graph | elements with `status: proposed`, by provenance (see Open 1) |
   | decisions | context graph | `DecisionRecorded` events: who, when, the action's params and the target's prior state |
   | evidence | context graph | `world` fixtures and `scenarios`, which the harness also runs as checks |
   | sources and history | context graph | `source` and `status` on elements; commits, approvals, check records |
   | open questions | context graph | the question behind each `undecided` cell; `status: unknown` |
   | preferences | context graph | not modeled |

## Consequences
- The README and `docs/how-it-works.md` use the two names, with this ADR as the definition.
- Reviewing a change means checking both graphs: what the world model will enforce (the change
  check, the harness) and why (the context the change cites).
- The proposal engine (M4) reads the context graph and writes only proposals. Accepting one is an
  approved commit, whichever surface it is accepted in.
- The query tools (M0b) cover the event store (ADR-0012). Joining commits, sources and the
  interview log into one queryable graph has no plan yet (Open 3); until then the context graph
  is a set of records linked by element keys, commit ids and event streams.

## Open
1. **Proposed elements are enforced.** `status` is provenance: nothing in the gate, the harness or
   the deploy reads it, so a proposed element is compiled and enforced like a confirmed one, and
   approving a commit does not refuse one that still holds proposed elements. Should
   `approve_commit` require every element to be confirmed?
2. **Decision records.** The notes ask a decision to carry its reason, expected outcome, scope
   and a condition for reviewing it again. A `DecisionRecorded` event carries a rationale only if
   the action declares a parameter for it, and none of the self domains' decision actions does.
   Add rationale, expected outcome and a re-review condition to the event?
3. **Edges in the context graph.** Which links are first-class: an element to its source, a rule
   to the decision that adopted it, an exception to the rule it bends, a commit to the
   observations that motivated it? Today only the first is declared, on every element.
4. **Whose agent acted, and who approves.** A rule cannot refer to an agent's principal (`actor`
   carries only its own id and roles), and nothing keeps a commit's author from approving it.
   Both are under *Left from reviews* in `docs/STATUS.md`. Until they are closed, "a proposal is
   never its own approval" holds only for the agent itself (`requires: human`).
5. **Runtime permissions.** Role holders and grants change without a commit. Should they be
   declared, or recorded as reviewed changes of their own?
6. **Preferences and exceptions.** Should preferences be modeled at all (as parameters, or as
   elements with a scope and an expiry)? And how is an exception granted, scoped and recorded?
