# ADR-0041: A domain keeps two graphs: the world model and the context graph

- Link: ② model is right, ⑤ evolves · Status: **proposed** (draft) · 2026-11-06 · to be decided
  by: SteamShon (definition from the researcher; drafted by the assistant)
- Builds on: ADR-0004 (provenance and status), ADR-0011 (the world model), ADR-0012 (event
  sourcing), ADR-0016 (authorization), ADR-0029 and ADR-0033 (commits, approval by merge)

## Context
Toprope already keeps two different kinds of knowledge, but the documents do not name the
difference:

- what a domain **is and allows**: objects, links, actions, states, the transition matrix,
  invariants and preconditions, roles and grants. This is the "world model" of ADR-0011. It is
  compiled into the Execution gate, the generated tools and the harness, and it is enforced.
- what **explains and changes** it: domain events and refused attempts, the interview log,
  elements an agent proposed but nobody confirmed, `records_decision` events, the `source` and
  `status` on every element, commits, approvals and check records. None of this is enforced by
  itself.

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
1. **Two graphs.** A domain keeps a **world model** and a **context graph**.
   - The **world model** holds what exists and what may happen: objects, links, actions,
     functions, states, and the **rules** and **permissions** adopted over them (matrix cells,
     invariants, preconditions; roles, actor rules, `requires: human`, grants). It is enforced:
     the gate, the generated tools and the harness come from it.
   - The **context graph** holds why the world model is as it is and what happened under it:
     **observations**, **memory**, **interpretations and hypotheses**, **preferences**,
     **decisions** with their reasons, and the **sources and history** of every element,
     including open questions and conflicts. It is not enforced. It explains, and it proposes.
2. **Only rules and permissions are enforced.** Of the six kinds, only rules and permissions live
   in the world model. The other four live in the context graph.
3. **The one way across.** Something in the context graph becomes a rule or a permission in the
   world model only through a reviewed change: a commit that passes its checks and that a person
   approves by merging it into `main` (ADR-0029, ADR-0033). Recording an observation, adopting a
   default in conversation, or an agent proposing an element changes nothing that is enforced.
   A proposal is never its own approval.
4. **Policies.** An adopted policy is a rule in the world model. Its candidates, its reasons, its
   exceptions and its change history are in the context graph. "New creatives go to a test
   campaign first" is a hypothesis in the context graph while the team checks it against the
   numbers, and a rule in the world model once a person approves it.
5. **Today's parts are mapped, not renamed.** Nothing in the declaration format or the stores
   changes with this ADR:

   | Kind | Graph | Where it is now |
   |---|---|---|
   | objects, links, actions, states | world model | the declaration |
   | functions | world model | function ports (ADR-0015), M0b |
   | rules | world model | confirmed matrix cells, invariants, preconditions |
   | permissions | world model | roles, actor rules, `requires: human`, grants (ADR-0016) |
   | observations | context graph | domain events, refused attempts, effect outcomes |
   | memory | context graph | the event log, the interview log |
   | interpretations, hypotheses | context graph | elements with `status: proposed` |
   | decisions | context graph | `records_decision` events |
   | sources and history | context graph | `source` and `status` on elements; commits, approvals, check records |
   | open questions, conflicts | context graph | `undecided` cells, `status: unknown` |
   | preferences | context graph | not modeled |

## Consequences
- The README and `docs/how-it-works.md` use the two names, with this ADR as the definition.
- Reviewing a change means checking both graphs: what the world model will enforce (the change
  check, the harness) and why (the context the change cites).
- The proposal engine (M4) reads the context graph and writes only proposals. It can never
  change the world model by itself.
- The query tools (M0b) are where the context graph becomes one queryable graph. Until then it
  is a set of records, linked by element keys, commit ids and event streams.

## Open
1. **Preferences.** Should they be modeled at all, and if so, are they inputs to an action's
   parameters, or a separate kind of element with a scope and an expiry?
2. **Decision records.** The notes ask a decision to carry its reason, expected outcome, scope
   and a condition for reviewing it again. `records_decision` today keeps who, when, inputs and
   rationale. Add expected outcome and a re-review condition?
3. **Edges in the context graph.** Which links are first-class: an element to its source, a rule
   to the decision that adopted it, an exception to the rule it bends, a commit to the
   observations that motivated it? Today only the first is declared on every element.
4. **Whose agent acted.** A rule cannot yet refer to an agent's principal (`actor` carries only
   the actor's own id and roles; *Left from reviews* in `docs/STATUS.md`). Permissions in the
   world model need it to say "not the proposer, nor the proposer's agent".
