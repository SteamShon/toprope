# Roadmap

Link: all. Each milestone is defined by the link it gives a verdict on. Work can span
several links, but a milestone ends with a verdict. Budget is ~10h+/week. Dates are targets.

| Milestone | Link | Question | Target |
|---|---|---|---|
| M0a | none (enabler) | Thin slice: declaration + semantics, model interpreter, Execution, event store, `toprope-server` MCP and authoring MCP, source readers, world map, harness (model, Execution, MCP), change check incl. log replay and in-flight check, incremental analysis; kernel services as declared effects so the self domains are generated end to end (ADR-0028) | 5–7 weeks |
| M1 | self-compile feasibility; ① and ⑥ piloted on the self domains, no link verdict (ADR-0030, ADR-0034) | Model Toprope's own Authoring and Delivery workflows by iterating, joined by a typed handoff (ADR-0022), and generate both. A pilot: do compile-time checks catch what natural-language skills and structured specs without a compiler cannot? | 4–5 weeks (re-estimated in M1's spec PR) |
| U | none (enabler) | Usability before M2 (ADR-0049): the change loop, getting started, the interview and its feedback, import and wrap; measured against a baseline | in four umbrellas; may run alongside M0b |
| M0b | none (enabler) | Surfaces and effects: representation compiler, `toprope-shell` (A2UI + CopilotKit), UI-level harness, GitHub brownfield adapter, embedded shape, migration plans, query tools, timers and functions, external sources other than `kernel`; regenerate the self domain's UI | 3–4 weeks |
| M2 | ③ judged, ① provisional, ② observed (dogfood, ADR-0054) | Do compile-time checks catch the seeded problems on a domain the researcher uses, and does the harness-passing software work in real use? | 3–4 weeks |
| M3 | ④ | Do people and agents act on the same meaning through the capsule? | 3 weeks |
| M4 | ⑤ | Do logs, proposals and decisions make domains better through use? (Runtime adapter, Aegra first, enters here) | 3 weeks |
| M5 | ⑥ (partial) | Do typed handoffs between domains preserve intent? Write-up, go public | 3 weeks |

**Order rationale (ADR-0019):** M1 needs only the thin slice, so M1 runs before the
surfaces and effects are built. That brings the first verdict to about 10–12 weeks (M0a 5–7 + M1 4–5,
after ADR-0022 added Delivery and ADR-0028 added kernel effects), down from about 15. This is a target at about 10 h/week, not a commitment.

**Usability before M2 (ADR-0049):** after M1 closes, a usability program removes the
friction M1 showed, so that M2's expert measures the claims and not the tools. It gives no
verdict, and M2's spec waits for it. Its themes, order and targets are in the ADR; progress is
in [`STATUS.md`](STATUS.md).

**Overrun rule:** if M0a runs past 6 weeks, cut it to what M1 strictly needs (semantics,
model interpreter, Execution, event store, MCP, authoring MCP, model and Execution-level
harness, structural/semantic/scenario/log-replay/in-flight checks) and move the rest to M0b.
Do not extend M0a.

**Milestone spec PRs (ADR-0019):** before a milestone starts, a PR freezes its
requirements, done criteria and verdict rules. Gold sets, probe suites and seeded change
lists are frozen by the researcher (AGENTS.md).

If a link is weakened or refuted, later milestones are re-planned before they start. Then
the claim status in the README is updated.

---

## M0a: Thin slice (no claim, 5–7 weeks incl. ADR-0028)

The hand-built kernel that M1 needs, and nothing more. Kernel code is kept small and listed,
so it is clear what was hand-built and what was generated.

1. **Spike (1–2 days, ADR-0017).** Run `toprope-server` serving a toy domain over MCP to
   Claude Code. Separately, render one A2UI view with one host component in a CopilotKit
   shell, which de-risks M0b early. If A2UI blocks, record the fallback (ADR-0017).
2. **Freeze the M1 instruments (researcher)**, using the templates and the validate/freeze
   tool in [`experiments/m1/`](../experiments/m1/README.md). The gold scenarios, the post-deploy probe
   suite, the change-request list with its seeded-problem key (written by intent), and the
   verdict rules, including the structured-spec arm. Freezing them *before* building the
   change checks keeps the seeded problems from being written around what the checks can
   catch.
3. **Semantics (`docs/semantics.md`) frozen**, then the **model interpreter** implementing
   it. It is the oracle.
4. **Domain schema v0**: objects, links, actions, the transition matrix, invariants
   (aggregate scope), world fixtures and scenarios, with provenance and status on every
   element.
5. **Domain compiler v0**: MCP tools (reads, one tool per action), execution checks, event
   schemas and projections, and the versioned domain interface.
6. **Execution + event store (ADR-0012)**: append-time enforcement, the invariant guard,
   optimistic concurrency, idempotency keys, denied attempts and decisions recorded. SQLite
   for tests, PostgreSQL for the server.
7. **Identity and actors (ADR-0016)**: persons and agents with `on_behalf_of` and grants;
   `requires: human`.
8. **Harness v0 (ADR-0010)**: small world, cell tests, invariant checks, gate-tier
   exploration, flows, replay parity, concurrency tests. It runs at the model, Execution and
   MCP levels, with parity and coverage reports.
9. **Change check v0 (ADR-0009, ADR-0018)**: structural, semantic conflict, scenario
   regression, **log replay**, **in-flight check** (stranded objects are listed; migration
   plans come in M0b), NL conflict warnings, and a preview (a server on copied state).
   M1's seeded changes include ones that break past logs and strand objects, so these
   checks must exist before M1.
10. **Incremental (ADR-0013)**: hashes, the dependency graph, the impact report,
    affected-only reruns, a result cache with the toolchain hash, and a background full run.
11. **World map (ADR-0020)**: `world-map.json` plus the `world_map` and `how_to_reach` MCP
    tools, derived from the declaration and harness results.
12. **Source readers**: repository (code, schema), markdown records, session transcripts,
    interview log, with redaction and local-only sources (ADR-0014). M1 Phase A needs them.
13. **Authoring MCP (ADR-0014, ADR-0017)**: tools for drafting, interview questions (defaults,
    grouped cells, priorities), answers and confirmations, so the user's own agent runs the
    interview. The authoring UI is CLI/YAML until self-compile produces one. This limit is
    accepted for M1, where the researcher is the only author.
14. **Handoffs (ADR-0022)**: the `handoffs` construct, delivered through an outbox after the
    sender's append, plus a **local deploy adapter** (preview → deploy to a local
    environment), so the M1 Delivery domain has real effects to model.

Done when, on the toy domain:
- every decided cell is covered at every level
- a deliberately broken generator template is caught while model-level regression still passes
- a seeded invariant-breaking transition is found by exploration as a minimal flow
- a race on one cell yields only outcomes the semantics allow
- a single-cell change meets the draft latency targets (impact report ≤ 2 s, affected
  harness ≤ 30 s, preview ≤ 30 s; set by the M1 verdict rules)
- the full run finds no selection miss.

## M1: Self-compile and a pilot of safe iteration (① ⑥ pilot, 4–5 weeks; ② and the ① verdict in M2 by ADR-0030, ADR-0034)

See [`experiments/M1-self-compile.md`](experiments/M1-self-compile.md).

- **Phase A**: model Toprope's own **Domain Authoring** and **Domain Delivery** workflows
  (ADR-0022) by iterating through system → records → interview → use, then generate both
  tools from them, joined by a typed handoff. They are planned through the staged interview
  with the researcher and confirmed by the researcher's sign-off, the regeneration check and
  the probes, with no gold set (ADR-0031). Recorded: human time and edits.
- **Phase B**: apply a frozen sequence of about 20 change requests with seeded conflicts and
  breakages to three arms: a natural-language skill (with LLM conflict review), a
  structured spec (the same YAML, with LLM review and no compiler), and the Toprope
  declaration (with compiler checks and a preview).

M1 runs on the M0a thin slice only.

Exit: verdicts on H-Iterate and H-Fidelity for both self domains, an observation on the
handoff (⑥ partial), and generated authoring and delivery tools v1. In M1 the tools are the
generated MCPs, driven by the user's agent, plus CLI/YAML. Their UIs are generated from the
same declarations after M0b.

Kill/pivot: if the NL arm with LLM review catches about as much as the compiler, the
compiler's value narrows to speed and previews, and this is recorded. If the self domain
cannot be modeled within thresholds, record which element types agents cannot draft and
narrow what is generated before M2.

## M0b: Surfaces and effects (no claim, 3–4 weeks, after M1)

1. **Representation compiler v0 (ADR-0008)**: interface + layers (defaults → base → host
   overlay) → deterministic A2UI views. Done when a representation-only change rebuilds
   without touching MCP, a domain change flags a broken view, and a host overlay injects one
   custom component.
2. **`toprope-shell` (ADR-0017)**: A2UI renderer + CopilotKit, with UI-level harness checks
   (A2UI message level).
3. **Greenfield backend over HTTP**, served by `toprope-server`, and the **embedded** shape
   (core imported by a host app).
4. **Brownfield adapter (ADR-0011)**: GitHub issues/labels in a sandbox repository, with an
   outbox, read-back and `UNKNOWN`; adapter-level harness checks (never cached).
5. **Read-only query tools** over the event store (ADR-0012), which M4 relies on.
6. **Migration plans (ADR-0018)**, plus the deploy gate conditions.
   Then **regenerate the self domain's authoring UI** from the M1 declaration, so M2 uses a
   fully generated authoring tool.
7. **World-map skill-tree view** in the shell, and the map diff in impact reports
   (ADR-0020).
8. **Timers (virtual clock in the harness), function ports with contract tests, external
   events and multi-party approvals (ADR-0015)**, as far as the M2 domain needs them.

Done when the toy domain runs as usable software through the shell and the greenfield API,
gates one GitHub effect, survives a state rename with stranded objects through a tested
migration, and its harness passes on every surface.

## M2: Dogfood domain (③ judged, ① provisional, ② observed, 3–4 weeks)

Use the self-compiled authoring tool from M1, not the hand-built kernel, to model a
second, everyday domain: the researcher's own investing in US stocks, on an Alpaca
paper-trading account (ADR-0054). The researcher takes every role (expert, owner, seeder, user); a preregistered
draw, not the researcher, decides which problems are seeded, and the key is sealed. **② is
observed here, not judged**: it needs a domain
expert who is not Toprope's builder (ADR-0030), so it stays untested until such a domain runs.
The held-out protocol built for M1 (`experiments/m1/interview-guide.md`, sealed validation,
fact keys, kernel-fact exclusion) is the starting point. M2's estimate is redone in its spec
PR, and M3 may use M2's gold only after M2's verdict is frozen.

Phase B (the change sequence vs. a natural-language skill and a structured spec) runs on this
domain and gives **a provisional ① result** (ADR-0054): the change requests come from the
researcher's diary of real use, the seeds from a preregistered draw, and the key is sealed; ①
stays `untested` in the claim-status table until problems seeded by someone who is not the
builder confirm it. M1's verdict rules are the starting point.

Questions:
- Is the second domain cheaper than the first?
- Did the generated tool hold up, or did it need hand fixes?

**③ works as built (H-Factory).** The researcher actually uses the generated software for
their investing (greenfield), together with one brownfield effect through the broker's
paper-trading API (an order, and its result read back), trading or checking every trading day
for at least two weeks (ADR-0054). Live changes during this period go through the
in-flight check and migration plans (ADR-0018). Only harness-passing builds are used. Every defect
is logged with its class:
- state-permission: an action allowed or denied differently from the declaration
- UX, performance, external API
- hand edits needed to generated code.

Exit: a provisional result on H-Iterate outside the self domain, an observation on H-Fidelity
(expert = builder, ADR-0054), and a verdict on H-Factory. ③ is
supported if harness-passing builds have zero state-permission defects and need no hand
edits. It is weakened if either fails. These thresholds are a draft, to be frozen by the
researcher before M2.

## M3: Shared language (④, 3 weeks)

On the M2 domain, give the same knowledge to agents in three ways:
- C0: docs plus generic data tools
- C1: hand-written typed tools with prose rules
- C2: capsule-generated MCP

The primary metric is intent errors (attempts and wrong conclusions, not only effects).
Also measured: task success, vocabulary alignment with the UI, stale actions after a fair
revision probe, and cost. A pilot gate runs first: C0 must produce ≥ 10% errors.
The M2 gold scenarios are reused as tasks.

Exit: verdict on H-Shared. If C1 ≈ C2, the gain is vocabulary, and the compiler's value
rests on ① (cost).

## M4: Evolution (⑤, 3 weeks)

- Record both kinds of decisions as first-class data: work decisions and domain-change
  decisions.
- Proposal engine: from logs and accumulated work decisions, propose model diffs with
  evidence. Humans decide in the generated UI. Accepted diffs regenerate the surfaces.
- The first `Runtime` adapter (Aegra) enters here for the unattended proposal engine
  (ADR-0017).
- Apply this to both domains, including the self domain, so the authoring tool improves
  itself. No self-approval, and the gold set and verdict checks stay outside the loop.

Exit: verdict on H-Evolve (proposal acceptance rate; accuracy and clarifications before and
after; over-generalization incidents).

## M5: Handoff and release (⑥ partial, 3 weeks)

- A typed handoff "experiment decided ship → delivery request" into a small third domain
  (code → product delivery), compared with a written note.
- State plainly what ⑥ needs that a personal project lacks: real teams and real handoffs.
- Write-up with findings, negative results and claims we cannot make. Choose a license
  (Apache-2.0 proposed) and make the repository public.

## Later

⑥ with real teams. Learning from accumulated work decisions. More brownfield adapters
(feature flags, ad APIs, internal services) beyond the M0 GitHub adapter. Adapters for other runtimes and hosts (Temporal, OpenDots). Comparison with automated harness
improvement (Harness²).
