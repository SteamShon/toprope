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

Toprope is a light, open foundation. It turns hidden workflows into a domain model that
people and agents both use, and keeps the model improving while it is used.

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
- **One model, two surfaces.** The model compiles into a *domain capsule*: MCP for agents
  and UI for people. Both get the same terms, rules and reasons.
- **Three things in one body:**
  - an authoring tool (a software factory) for building and changing domains fast
  - the execution path the work runs through, because actions go through the model
  - a layer over existing systems that owns meaning, approval and record, while existing
    code, APIs and databases perform the effects
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
                            └─────────────► event log ─────────────────────────┘
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
③ shared language   MCP and UI generated from the model let people and agents act on the same meaning
      ↓
④ evolves           use accumulates decisions, and the model keeps improving
      ↓
⑤ org productivity  handoff delay and re-explanation between people go down
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
| Flow test harness | generated from the same scenarios, run against the generated MCP, UI views, Execution and adapters; the same flow must give the same outcome on every surface (ADR-0010) | deterministic |
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
| ③ | H-Shared | Agents working through capsule-generated actions make fewer meaning errors than agents given the same knowledge as docs plus generic tools. | Docs ≈ capsule, or hand-written typed tools ≈ capsule (in which case the gain is vocabulary only). |
| ④ | H-Evolve | Log → proposal → human decision improves accuracy and reduces clarifications in later use. | Confirming costs more than it saves, or proposals are mostly noise. |
| ⑤ | H-Handoff | A typed handoff between domains loses less intent than a written note. | Good notes perform the same. |

Thresholds are initial. Each experiment preregisters its own. ⑤ can only be tested in part
without a real organization, and that limit is stated wherever ⑤ is discussed.

## 5. Distinctions kept throughout

- Meaning (model) ≠ execution (runtime) ≠ surfaces (MCP, UI).
- Observing ≠ interpreting ≠ deciding ≠ being authorized to act.
- An agent proposing a change ≠ that change being approved. **No self-approval**, and this
  matters most in self-compile.
- An action reported as successful ≠ its effect having happened. Timeouts are `UNKNOWN`.
- A rule being enforced ≠ the rule being right.

## 6. Non-goals

- A full ontology platform, a hosted multi-tenant service, or a marketplace.
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
