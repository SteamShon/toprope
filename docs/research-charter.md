# Research Charter

Version 0.2, 2026-11-04 (supersedes 0.1, which framed the work as agent guardrails; see ADR-0007).

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

## 2. Thesis

1. **Workflow ≡ domain.** A workflow can be modeled as a domain: objects (Hypothesis,
   Experiment, Metric, Decision), links between them, and actions with preconditions,
   effects and approval roles. This is the same move as an ontology plus action types.
2. **One model, two surfaces.** The model is compiled into a *domain capsule* that
   generates the agent surface (typed MCP tools whose descriptions and checks come from the
   model) and the human surface (a UI over the same objects and actions). The claim is that
   this is how people and agents come to perceive the work in **the same language**.
3. **Software-factory loop.** The domain author defines the model, uses the generated
   UI/MCP, and every run is logged. Agents propose model changes from the logs, and the
   author decides. The domain improves through use, and decisions accumulate as versioned
   state.
4. **Enforcement is a consequence, not the goal.** Because actions run through the model,
   preconditions and approvals hold on the execution path. This matters, but the research
   is about shared meaning and accumulation, not safety.

## 3. Research questions

- **RQ1, shared language.** Does an agent that works through capsule-generated typed actions
  make fewer *meaning* errors on a workflow than one given the same knowledge as a process
  document plus generic data tools? Does it explain its reasoning in the same terms the
  human UI shows?
- **RQ2, authoring cost.** With the generate → use → fix loop, how long does it take a domain
  author to reach a usable domain? What do the second and third changes cost compared with
  the first build?
- **RQ3, accumulation.** Do agent proposals mined from run logs, once the author decides on
  them, reduce clarifying questions and errors in later runs without over-generalizing?
- **RQ4, handoff.** When two domains hand off (experiment → product delivery), does a typed
  handoff preserve intent better than a written handoff note?
- **RQ5, boundary.** What does the model fail to capture? Which judgments must stay with
  people? Where do the execution guarantees end (bypass paths, `UNKNOWN` effects)?

## 4. Hypotheses and what would weaken them

| ID | Hypothesis | Weakened if |
|---|---|---|
| H-Shared | Capsule-generated typed actions reduce workflow-meaning errors compared with docs plus generic tools, at equal information. | Docs plus generic tools come within noise of the capsule. Or hand-written typed tools with prose semantics match the capsule, in which case the gain is from vocabulary rather than the compiled model. |
| H-Factory | The generate/use/fix loop gets a domain to usable faster than hand-building tools and UI, and later changes stay cheap. | Each change needs as much manual rework as a hand-built stack, or the author mostly fights the generator. |
| H-Accumulate | Log → proposal → human decision makes later runs need fewer clarifications and make fewer errors. | Confirming proposals costs more than it saves, or most proposals are noise or over-generalizations. |
| H-Handoff | Typed cross-domain handoffs lose less intent than notes. | Good notes perform the same. |

Each hypothesis is tested separately. Success of one does not imply another.

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
