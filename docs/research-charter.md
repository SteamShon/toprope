# Research Charter

Version 0.3, 2026-11-04. 0.2 reframed the work from agent guardrails to organizational workflows (ADR-0007). 0.3 adds the agreed definition, the claim chain and the load-bearing bet (ADR-0011, ADR-0012).

## 1. Problem

Agents have raised individual productivity, especially in coding. Organizational
productivity has not followed. The bottleneck has moved to the **workflows between
people**: turning code into a shipped product change, or turning a hypothesis into an
experiment that moves a metric and into a ship/kill decision.

These workflows are mostly implicit:

- **Unwritten.** Preconditions, approval roles, timing rules ("don't read out before two
  full weeks", "guardrail regressions block shipping") are passed on orally.
- **Not shared between people and agents.** Each side holds its own picture of the work.
  An agent given a wiki page and database access must re-infer the meaning every time.
- **Not accumulated.** Each decision (approve, stop, ship, kill, make an exception) is made
  in a chat or a meeting. No structured record links it to its inputs, so the organization
  cannot learn from it and agents cannot reuse it.

Result: agents can do individual steps but cannot carry the workflow, and humans keep
doing the connective work by hand.

## 2. What Toprope is

Toprope is a light, open foundation that turns the hidden workflows between people into a
domain model that people and agents both use, and keeps that model improving while it is
used.

- **Who authors**: everyone involved. Agents draft, domain experts and developers refine
  and decide. Experts answer questions about the work, never about formats or builds.
- **What it is**: three things in one body:
  - an authoring tool (a software factory) for building and changing domains fast
  - the execution path the work runs through, because actions go through the model
  - a layer over existing systems that owns meaning, approval and record, while existing
    code, APIs and databases perform the effects
- **Workflow ≡ domain**: objects, links and actions (preconditions, effects, roles), in the
  spirit of an ontology plus action types. One model compiles into a *domain capsule*: MCP
  for agents and UI for people.
- **Two kinds of decisions accumulate, with equal weight**:
  - *work decisions* (approve, ship, kill, exception), recorded with their inputs
  - *domain-change decisions* (change a rule), recorded with their evidence

  Accumulated work decisions become the evidence for proposing domain changes.
- **Raw material, in order of how easily it can be automated**: draft from existing
  systems (code, schema, APIs) → enrich from existing records (docs, issues, chats) →
  raise accuracy by interviewing the owner → keep improving through use.
- **Bets that differ from Foundry-style ontologies**: authoring is cheap; agents are
  first-class users; the domain evolves through operation; it is light and open, so small
  teams can use it.
- Enforcement follows from actions running through the model. It is a property, not the goal.

## 3. The claim chain

Toprope's thesis is a chain. Each link only matters if the previous one holds.

```
① can be built     an implicit workflow can be turned into a domain model cheaply
② model is right   the model captures how the work actually runs
③ shared language  MCP and UI generated from it let people and agents act on the same meaning
④ evolves          use accumulates decisions and the model improves
⑤ org productivity handoff delay and re-explanation between people go down
```

**The load-bearing bet is ① + ②** (ADR-0011). If domains cannot be built cheaply, nobody
builds one, and ③–⑤ never start. It is also the most uncertain link and the one where
Toprope differs most from existing ontology platforms. ③ comes second, because Foundry-style
deployments already give some evidence for it.

Research questions, one per link:

- **RQ1 (①)**: Starting from existing systems, records, the owner and use, how much human
  time does it take to reach a usable domain? What do later changes cost?
- **RQ2 (②)**: How accurately does the resulting model answer held-out workflow questions?
  How many of its rules are unsupported?
- **RQ3 (③)**: Do agents working through capsule-generated actions make fewer meaning errors
  than agents given the same knowledge as docs plus generic tools?
- **RQ4 (④)**: Do proposals mined from logs and work decisions, once a human decides on
  them, improve the model and reduce later clarifications?
- **RQ5 (⑤, partial)**: Does a typed cross-domain handoff preserve intent better than a note?
- **RQ6 (boundary)**: What do models fail to capture, which judgments must stay with people,
  and where do the execution guarantees end?

## 4. Hypotheses and what would weaken them

| ID | Link | Hypothesis | Weakened if |
|---|---|---|---|
| H-Author | ① | The system → records → interview → use pipeline reaches a usable domain in ≤ 4 human hours, and later changes take ≤ 30 min. | Human time is mostly spent correcting agent drafts, or changes need hand edits to generated surfaces. |
| H-Fidelity | ② | The model reaches ≥ 80% held-out scenario accuracy with ≤ 10% unsupported rules. | Accuracy plateaus below 70%, or agents invent rules faster than humans can catch them. |
| H-Shared | ③ | Capsule-generated actions reduce meaning errors compared with docs plus generic tools. | Docs ≈ capsule, or hand-written typed tools ≈ capsule (in which case the gain is vocabulary only). |
| H-Evolve | ④ | Log → proposal → decision improves accuracy and reduces clarifications. | Confirmation costs more than it saves, or proposals are mostly noise. |
| H-Handoff | ⑤ | Typed handoffs lose less intent than notes. | Good notes perform the same. |

Thresholds are initial and preregistered in each experiment document. Success of one
hypothesis does not imply another.

## 5. Distinctions kept throughout

- The workflow's *meaning* (model) ≠ its *execution* (runtime) ≠ its *surfaces* (MCP, UI).
- Observing ≠ interpreting ≠ deciding ≠ being authorized to act.
- An agent proposing a model change ≠ that change being approved. No self-approval.
- An action reported as successful ≠ its effect having happened. Timeouts are `UNKNOWN`.
- A rule being enforced ≠ the rule being right.

## 6. Non-goals

- Rebuilding a full ontology platform, a hosted multi-tenant service, or a marketplace.
- Choosing a durable runtime (Temporal, LangGraph) or host (OpenDots) before a milestone
  needs one (ADR-0006).
- Response-model or policy learning (thread C). The accumulated decision log is its future
  dataset, but learning from it is out of scope for now.
- Monetization as a success criterion. Reproducing a former employer's code or data.

## 7. Evaluation principles

- **Fair baselines.** Same model, same information, same task. The strongest reasonable
  baseline is included, not only a weak one.
- **No tautological metrics.** When the treatment blocks invalid actions by construction,
  measure *intended* errors (attempts and wrong conclusions), task success and cost, not
  only effects.
- **Pilot first.** Before a full run, a small pilot must show the baseline actually makes
  errors. Otherwise redesign the tasks.
- **Preregister.** Metrics and verdict rules are fixed before results are seen.
- **Count human cost and money.** Count authoring, reviewing and maintenance time, and
  estimate API cost before running.
- **Report negative results** and the claims we can no longer make.
