# ADR-0042: The concepts Toprope lacks, and where each would go

- Link: ① iterate safely, ② model is right, ③ works as built, ⑤ evolves · Status: **proposed** ·
  2026-11-06 · decided by: (pending) SteamShon (drafted by the assistant)
- Builds on: ADR-0011 (correctness layer), ADR-0012 (event sourcing), ADR-0015 (timers,
  functions), ADR-0016 (authorization), ADR-0041 (world model and context graph)

## Context
[`docs/concepts.md`](../concepts.md) names Toprope's parts. Comparing them with what other work on
agents and graphs relies on (the Year of the Graph newsletter, vol. 32, autumn 2026, and the
sources it collects; the researcher's own problem definition) shows six concepts Toprope does not
have yet:

1. **Obligations**: what must happen, by when. Toprope controls what may and may not be done, not
   what must be.
2. **Goal, decision, action, outcome**: decisions and actions are recorded; the goal a decision
   served and the outcome it led to are not, nor the link between them.
3. **Read control**: Toprope controls what an actor may *do*, not what it may *see*.
4. **Freshness**: whether a confirmed element is still true. Who confirmed it is recorded; when,
   and until when it holds, are not.
5. **Two clocks**: the time a fact held in the world, as distinct from the time the system
   recorded it. Events carry only the second (`at`).
6. **Entity resolution**: knowing that two records in two systems are the same thing.

Three are partly present and stay with their milestones: classifying a contradicting input as a
block, an exception or a revision, and a `revises` link between decisions (the M4 decision-record
spec); per-element owners (M2, ADR-0032); compacting logs (not needed at current volumes).

This ADR decides, for each of the six, whether Toprope takes it on, in which part, and when. Each
section gives the options and a recommendation; the researcher decides.

## Open, with recommendations

### 1. Obligations
- **Options.** (a) A new construct, `obligations`, beside rules. (b) Deadlines as timers, already
  defined (docs/domain-schema.md, Timers; ADR-0015): a timer fires a "deadline passed" action as
  `system`, and the matrix says what that action does in each state. (c) Leave obligations to the
  host.
- **Recommendation: (b).** An obligation is a state that must not last past a deadline, so it is
  a timer plus a matrix row: no new construct, and the harness's virtual clock already tests it.
  What "overdue" means (escalate, block further actions, notify) is the domain's own declared
  action. Built with timers in M0b.

### 2. Goal, decision, action, outcome
- **Options.** (a) A new `Goal` object in every domain. (b) Use what is declared: a domain's
  `purpose` (problem, success metric) is its goal; a decision records an expected outcome and a
  condition for reviewing it; an observed outcome is an event that names the decision it follows.
  (c) Leave it to analytics outside Toprope.
- **Recommendation: (b), in the M4 decision-record spec.** ADR-0041 already put the expected
  outcome and the re-review condition there; this adds the link back from an outcome to its
  decision (an event field naming the decision event). The proposal engine is the first reader,
  so its spec is where the shape is right.

### 3. Read control
- **Options.** (a) Declared visibility: per object or property, the roles that may read it,
  enforced by every surface that reads (the query tools, the MCP read tools, the guide's
  examples). (b) Leave it to the host's access control. (c) Only redaction of authoring sources,
  as now.
- **Recommendation: (a), declared now as a schema construct, built with the query tools (M0b).**
  Read control matters as soon as agents can query history, which is what the query tools do;
  building them without it would expose every decision to every agent. Defining it in the
  schema first keeps the construct reviewable before any surface depends on it.

### 4. Freshness
- **Options.** (a) Elements carry `confirmed_at` and an optional `review_by`; the change check
  warns about elements past `review_by`. (b) A separate freshness store. (c) Nothing until a
  domain needs it.
- **Recommendation: (a), as warnings, in M2.** `confirmed_at` is derivable today from the
  interview log's confirm entries, so it costs little; `review_by` is set by the person who
  confirms. A stale element is a warning, never a refusal: a rule does not stop holding because
  a date passed, but someone should look. M2 is the first domain whose rules change for reasons
  outside Toprope, where this starts to matter.

### 5. Two clocks
- **Options.** (a) Every event gains a valid time beside `at`. (b) Two narrower steps: rules
  already have a valid time, because each event records the `domain_version` it was decided
  under and deployments record when each version went live, so "judged by the rule in force
  then" is answerable now; and facts that come from outside (adapter read-backs, external
  events) carry the time they were observed as well as the time they were recorded. (c) Nothing.
- **Recommendation: (b).** Document the first now; add the observed time with the adapters
  (M0b), where facts first arrive late. Rules that take effect at a future date stay out until a
  domain asks for them.

### 6. Entity resolution
- **Options.** (a) A resolution service in the kernel. (b) Each adapter maps its system's
  identifiers to Toprope objects, declared per object and system; a mapping is recorded as an
  event with its source; an ambiguous match is `UNKNOWN`, and a person decides; nothing is merged
  silently. (c) Leave it to the host.
- **Recommendation: (b), with the first adapter (M0b).** Resolution is specific to each system,
  so it belongs at the boundary to that system; recording each mapping keeps it in the context
  graph, and refusing to guess follows the rule already used for effects (`UNKNOWN` until a
  read-back says otherwise).

## Consequences (if the recommendations are accepted)
- No new kernel concept in M1. Obligations and two clocks need nothing new beyond what is defined
  (timers) and what is recorded (`domain_version`, deployments).
- The schema gains, as *defined* constructs: read visibility (M0b), `review_by` on elements
  (M2), and identity mappings on adapters (M0b).
- The M4 decision-record spec owns goals, expected outcomes, re-review conditions, the link
  from outcome to decision, and the block / exception / revision classification.
- `docs/concepts.md` lists each concept under the part it belongs to once it is built.
