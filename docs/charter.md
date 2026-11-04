# Charter

Link: all. Version 1.0, 2026-11-04.

## 1. Problem

Agents raised individual productivity, coding most of all. Organizational productivity did
not follow. The bottleneck moved to the workflows **between people**: turning code into a
shipped product change, or turning a hypothesis into an experiment, a moved metric and a
ship/kill decision.

These workflows are implicit:

- **Unwritten.** Preconditions, approval roles and timing rules are passed on orally.
- **Not shared.** People and agents each hold their own picture of the work, and an agent
  given a wiki and database access re-infers the meaning every time.
- **Not accumulated.** Decisions are made in chats and meetings. Nothing structured links
  them to their inputs, so neither agents nor the organization can learn from them.

## 2. What Toprope is

Toprope is a light, open **correctness layer and software factory**. It turns hidden
workflows into a domain model that people and agents both use. From that model it
produces working software, and it keeps the model improving while it is used.

```
Intelligence   agents (Claude Code, Codex, any MCP client) and people
      │        perceive the world model and its allowed boundary
      ▼
Toprope        correctness layer: declaration, transition matrix, invariants, Execution gate,
               harness-verified generated MCP, UI and backend
      │        only allowed actions pass, through adapters
      ▼
Effects        greenfield: the backend Toprope generates · brownfield: existing servers, APIs, DBs
```

On its own the correctness layer means little. It matters when it sits between an
intelligence layer that proposes actions and an effect layer that performs them (ADR-0011).

- **Premise: nobody can define a domain correctly in one go.** Domains become right only
  through many iterations. Each iteration must be extremely cheap and testable, and rebuilds
  will be very frequent.
- **The compiler's core job is change safety, not code generation.** When a domain expert
  changes something, the compiler compares it with the existing declaration and reports
  **before deployment** what breaks or conflicts. It also lets the expert try the change in a
  preview. A rule added to a natural-language skill cannot be checked against the existing
  text until it is deployed and used. Declaring the domain moves that check to compile time.
- **Workflow ≡ domain.** A workflow is modeled as objects, links and actions
  (preconditions, effects, roles), in the spirit of an ontology plus action types.
  Each stateful object has a **transition matrix** and **invariants** (DDD-style). Domain
  experts do not think in matrices, so the interview fills them cell by cell in plain
  questions. The compiler then generates a harness that checks the whole matrix, which no
  person can test by hand.
- **One model, two surfaces.** The model compiles into a *domain capsule*: MCP for agents
  and UI for people. Both get the same terms, rules and reasons.
- **Three things in one body:**
  - a **software factory**: a person who is not a developer defines the world model through
    the interview, and the output is software they can actually use (internal tools,
    external tools, consumer products). It is not a spec handed to developers.
  - the **correctness layer** the work runs through, because every action goes through the
    model
  - a layer over effects: for **greenfield**, the backend and store that Toprope generates;
    for **brownfield**, existing code, APIs and databases behind adapters
- **Everything is a record (event sourcing).** Domain events, decisions, denied attempts,
  exceptions, effect outcomes and domain changes are stored as events. Agents can query them,
  which is how the next policy or domain improvement gets proposed (ADR-0012). The
  implementation pattern is DDD + invariants + transition matrix + event sourcing.
- **Writing the code is nearly free.** It is generated, and it is trusted because the
  harness checks every allowed and denied state transition, not because a call graph was
  tested. This is the researcher's experience with DDD, transition matrices, invariants and
  coding agents (*observed, not measured*). It is tested as link ③.
- **Everyone authors.** Agents draft. Domain experts and developers refine and decide.
  Experts are asked about the work, never about formats or builds.
- **Raw material, in order of how easily it can be automated:** draft from existing
  systems (code, schema, APIs) → enrich from records (docs, issues, chats) → raise
  accuracy by interviewing the owner → keep improving through use.
- **Two kinds of decisions accumulate, with equal weight:**
  - *work decisions* (approve, ship, kill, exception), recorded with their inputs
  - *domain-change decisions* (change a rule), recorded with their evidence

  Accumulated work decisions become the evidence for proposing domain changes.
- **Self-compile.** Authoring a domain is itself a workflow, so Toprope's own authoring
  process is the first domain modeled. The authoring tool is then generated from that
  model and used on other domains.
- **Different from Foundry-style ontologies:** authoring is cheap, agents are first-class
  users, the domain evolves through operation, and it is light and open enough for small
  teams.
- Enforcement follows from actions running through the model. It is a property, not the goal.

```
            ┌──────────── domain model (objects · links · actions) ◄──────────┐
            │ compile                 │ compile                         human decides
            ▼                         ▼                                       │
      MCP for agents            UI for people                        agent proposes diff
            └──────► the workflow runs ◄┘                                      │
                            └─────────────► event store ───────────────────────┘
```

## 3. The claim chain

```
P0 premise          nobody can define a domain correctly in one go; it is found by iterating
      ↓
① iterate safely    a domain can be changed cheaply and safely: breakage and conflicts are
                    caught at compile time and the change can be tried before deployment
      ↓
② model is right    through those iterations, the model comes to capture how the work runs
      ↓
③ works as built    software generated from a harness-passing declaration works in real use;
                    writing the code is nearly free (the software factory)
      ↓
④ shared language   MCP and UI generated from the model let people and agents act on the same meaning
      ↓
⑤ evolves           use accumulates decisions, and the model keeps improving
      ↓
⑥ org productivity  handoff delay and re-explanation between people go down
```

P0 is taken as given and is not tested directly. M1 will report whether the model was
right on the first attempt, as a sanity check on it. Each link only matters if the previous
one holds. **① + ② is the load-bearing bet.** If changing a domain is expensive or unsafe,
nobody iterates, and the model never becomes right. This is also where Toprope differs most
from natural-language skills, whose changes cannot be checked before deployment, and from
ontology platforms that are expensive to change.

### What "iterate safely" requires of the compiler (ADR-0009)

| Check | Example | Nature |
|---|---|---|
| Structural | a removed field is still referenced by an action or a representation | deterministic |
| Semantic conflict | two rules allow and forbid the same case; unreachable states; dead actions | deterministic |
| Scenario regression | an example scenario attached to the domain changes outcome | deterministic |
| Generated harness | from the declared **transition matrix**, **invariants**, a **small world** grown from the expert's examples, and example flows: every cell tried, invariants checked after every step, bounded exploration for violations (fixed seed and example count in the deploy gate; deeper exploration in the background). It runs against the generated MCP, UI views, Execution and adapters, and the same test must give the same outcome on every surface (ADR-0010) | deterministic |
| Impact analysis | before anything runs: "changes 2 cells; affects 14 cell tests, 1 invariant, 2 views, 3 flows". Only the affected set is rebuilt and retested, and cached results cover the rest (ADR-0013) | deterministic |
| Log replay | "with this change, 12 past actions would have been blocked" | deterministic |
| Natural-language conflict | descriptions or judgment rules contradict each other | LLM, reported as warnings |

Every change also produces a **preview build**: generated MCP and UI on a copy of the state.
The expert can try the change there before deploying it. The generated flow harness runs
against that build, because generated code that was never exercised is not known to work.

## 4. Hypotheses

| Link | ID | Hypothesis | Weakened if |
|---|---|---|---|
| ① | H-Iterate | Compile-time checks catch most seeded conflicts and breakages **before deployment**. A natural-language skill baseline, even with an LLM conflict review, catches clearly fewer. A change goes from edit to validated preview in minutes. | The baseline with LLM review catches about as many; or most breakages surface only after deployment; or false alarms are so frequent that experts ignore the checks. |
| ② | H-Fidelity | Over the iterations, held-out scenario accuracy reaches ≥ 80% with ≤ 10% unsupported rules. Accuracy rises with the number of iterations, not with the first draft. | Accuracy plateaus below 70%, or agents invent rules faster than checks and humans catch them. |
| ③ | H-Factory | Software generated from a declaration that passes the harness (every matrix cell, every invariant, parity) has **no state-permission defects** in real use: no action allowed or denied differently from the declaration. Other defects (UX, performance, external API quirks) are counted separately and stay few. No hand edits to generated code are needed. | Harness-passing builds show state-permission defects in use, or routinely need hand edits to work, or other defect classes dominate so much that "nearly free" does not hold. |
| ④ | H-Shared | Agents working through capsule-generated actions make fewer meaning errors than agents given the same knowledge as docs plus generic tools. | Docs ≈ capsule, or hand-written typed tools ≈ capsule (in which case the gain is vocabulary only). |
| ⑤ | H-Evolve | Log → proposal → human decision improves accuracy and reduces clarifications in later use. | Confirming costs more than it saves, or proposals are mostly noise. |
| ⑥ | H-Handoff | A typed handoff between domains loses less intent than a written note. | Good notes perform the same. |

Thresholds are initial. Each experiment preregisters its own. ⑥ can only be tested in part
without a real organization, and that limit is stated wherever ⑥ is discussed.

## 5. Distinctions kept throughout

- Meaning (model) ≠ execution (runtime) ≠ surfaces (MCP, UI).
- Observing ≠ interpreting ≠ deciding ≠ being authorized to act.
- An agent proposing a change ≠ that change being approved. **No self-approval**, and this
  matters most in self-compile.
- An action reported as successful ≠ its effect having happened. Timeouts are `UNKNOWN`.
- A rule being enforced ≠ the rule being right.

## 6. Non-goals

- A full ontology platform, a hosted multi-tenant service, or a marketplace. (How the
  correctness layer is *deployed* for one team is an open question, ADR-0011.)
- Choosing a durable runtime or host before a milestone needs one.
- Learning response models from outcomes. The decision log is a future dataset for that.
- Monetization as a success criterion.

## 7. Evaluation principles

- **Fair baselines**, including the strongest reasonable one.
- **No tautological metrics.** When the treatment blocks invalid actions by construction,
  count intended errors and task success, not only effects.
- **Pilot first.** Check that the baseline produces a measurable signal before a full run.
- **Preregister** metrics and verdict rules before results. Freeze gold sets before drafting.
- **Count human time and money**, not only tokens.
- **Report negative results** and the claims we can no longer make.

## References

- Palantir Foundry Ontology: object, link and action types (conceptual reference)
- Model Context Protocol (agent surface)
- Harness²: Recursive Agent Harnessing for an Open World, arXiv:2610.14224v1 (comparison
  for automated improvement loops)
- Temporal, LangGraph (runtime candidates); CopilotKit OpenDots (host candidate)
