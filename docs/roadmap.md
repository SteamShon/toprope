# Roadmap

Link: all. Each milestone is defined by the link it gives a verdict on. Work can span
several links, but a milestone ends with a verdict. Budget is ~10h+/week. Dates are targets.

| Milestone | Link | Question | Target |
|---|---|---|---|
| M0 | none (enabler) | The hand-built kernel: compiles a domain into working software (MCP, UI, event-sourced backend), generates its harness incrementally, and gates one brownfield API | 6–8 weeks (M0a + M0b) |
| M1 | ① ② (self) | Model Toprope's own authoring workflow by iterating; do compile-time checks catch what natural-language skills cannot? | 3–4 weeks |
| M2 | ① ② ③ (dogfood) | Does the same hold on another domain, and does the harness-passing software work in real use? | 3–4 weeks |
| M3 | ④ | Do people and agents act on the same meaning through the capsule? | 3 weeks |
| M4 | ⑤ | Do logs, proposals and decisions make domains better through use? | 3 weeks |
| M5 | ⑥ (partial) | Do typed handoffs between domains preserve intent? Write-up, go public | 3 weeks |

If a link is weakened or refuted, later milestones are re-planned before they start. Then
the claim status in the README is updated.

---

## M0: Kernel (no claim, 6–8 weeks, re-estimated after ADR-0012 and ADR-0013)

The bootstrap is the hand-built kernel that later milestones generate from. ADR-0010 to
ADR-0013 made it much larger than the first estimate. At ~10h/week it is split so that each
part ends with something runnable:
- **M0a, 3–4 weeks: core loop.** Spike, schema, domain compiler (MCP and event-sourced
  backend), Execution with the invariant guard, event store, harness v0 at the model,
  Execution and MCP levels, incremental impact analysis and result cache, and the M1
  instruments frozen first.
- **M0b, 3–4 weeks: surfaces and effects.** Representation compiler and A2UI views, UI-level
  harness checks, the change-check pipeline's remaining checks (log replay, NL conflict),
  the GitHub brownfield adapter, both hosting shapes, and the generated query tools.

If M0a runs past 5 weeks, cut M0b scope before starting M1, rather than extending M0.

Items below are listed by topic; the M0a/M0b split above decides the order.

- **Spike first (1–2 days, ADR-0007):** Aegra running a toy graph, an MCP server mounted on
  its custom routes with auth checked, CopilotKit connected, one A2UI view rendered from a
  toy representation, plus one host-injected custom component. If any part fails, record it and choose a fallback before building the kernel.
- Stack: pure-Python domain core (`uv`), Aegra as the runtime adapter, TypeScript frontend.
- Domain schema v0 with provenance and status on every element (`domain-schema.md`).
- Domain compiler v0: domain → MCP (reads, plus one tool per action with preconditions),
  execution checks, and a versioned domain interface.
- Representation compiler v0 (ADR-0008): interface + layers (defaults → base → host overlay)
  → deterministic A2UI views. Done when:
  - a representation-only change rebuilds without touching MCP
  - a domain change flags a broken view
  - a host overlay injects one custom component.
- **Freeze the M1 instruments first (researcher):** the gold scenarios, the post-deploy probe
  suite, the change-request list with its seeded-problem key (written by intent), and the
  verdict rules. Freezing them *before* building the change checks keeps the seeded problems
  from being written around what the checks can catch (M1 risks).
- **Incremental from the start (ADR-0013)**: content hashes, the declaration → artifact → test
  dependency graph, an impact report before anything runs, affected-only rebuild and
  retest, a result cache keyed by input hashes, and a background full run that counts
  selection misses. Done when a single-cell change on the toy domain meets the draft
  targets (impact report ≤ 2 s, affected harness ≤ 30 s, preview ≤ 60 s) and a full run
  finds no selection miss.
- **Change-check pipeline v0 (ADR-0009)**, the core of the compiler: diff against the current
  version; structural and semantic-conflict checks; scenario regression; log replay; LLM
  natural-language conflict warnings; preview build. Done when an edit reaches a validated
  preview in minutes on the toy domain.
- **Harness v0 (ADR-0010)**: transition matrix and invariants in the schema; a small world
  grown from fixtures; generated cell tests, invariant checks, bounded exploration
  (Hypothesis) and example flows, run at the model, Execution and MCP levels plus A2UI
  message-level view checks; parity and coverage reports. Done when, on the toy domain:
  - every decided cell is covered
  - a deliberately broken generator template is caught while model-level regression
    still passes
  - a seeded invariant-breaking transition is found by exploration and reported as a
    minimal flow.
- **Event store (ADR-0012)**: event-sourced greenfield backend; schemas, projections and
  append-time enforcement generated from the declaration; denied attempts, decisions and
  effect outcomes recorded; generated read-only MCP query tools; replay parity checked by
  the harness.
- Source readers: repository, markdown records, session transcripts, interview log.

- **Greenfield backend (ADR-0011)**: the compiler also generates a domain API over the event
  store and its projections (ADR-0012), so the toy domain runs as usable software with no other system.
- **Brownfield adapter (ADR-0011)**: one `EffectAdapter` to GitHub issues/labels in a sandbox
  repository, with read-back and `UNKNOWN` on timeout. Adapter-level harness checks run
  against it.
- **Hosting shapes (ADR-0011)**: run the same Execution core as (a) a gateway in front of the
  GitHub adapter and (b) embedded in the generated backend. Record the cost of each, and
  write the hosting decision as its own ADR.

Exit: a small toy domain compiles to working MCP, UI and greenfield backend, its generated harness passes
on every surface, and calls are logged.
Kernel code is kept small and listed, so it is clear what was hand-built and what was
generated.

## M1: Self-compile and safe iteration (① ②, 3–4 weeks)

See [`experiments/M1-self-compile.md`](experiments/M1-self-compile.md).

- **Phase A**: model Toprope's own authoring workflow by iterating through system → records
  → interview → use, then generate the authoring tool from it. Recorded: accuracy over
  iterations and first-draft accuracy (a P0 sanity check).
- **Phase B**: apply a frozen sequence of about 20 change requests with seeded conflicts and
  breakages to two arms: a natural-language skill (with LLM conflict review) and the
  Toprope declaration (with compiler checks and a preview).

Exit: verdicts on H-Iterate and H-Fidelity for the self domain, and a generated authoring
tool v1.

Kill/pivot: if the NL arm with LLM review catches about as much as the compiler, the
compiler's value narrows to speed and previews, and this is recorded. If the self domain
cannot be modeled within thresholds, record which element types agents cannot draft and
narrow what is generated before M2.

## M2: Dogfood domain (① ② replicated, ③, 3–4 weeks)

Use the self-compiled authoring tool from M1, not the hand-built kernel, to model a
second, everyday domain. The candidate is the experiment lifecycle (hypothesis → design →
approval → launch → readout → ship/kill), sourced from an OSS experimentation platform
plus the researcher as owner. Same metrics and gold-set procedure as M1.

Phase B (the change sequence vs. a natural-language skill) is repeated on this domain.

Questions:
- Is the second domain cheaper than the first?
- Did the generated tool hold up, or did it need hand fixes?

**③ works as built (H-Factory).** The researcher actually uses the generated software for
the experiment lifecycle (greenfield), together with one brownfield effect through the
GitHub adapter, for at least two weeks. Only harness-passing builds are used. Every defect
is logged with its class:
- state-permission: an action allowed or denied differently from the declaration
- UX, performance, external API
- hand edits needed to generated code.

Exit: verdicts on H-Iterate and H-Fidelity outside the self domain, which is the stronger
test because the self domain is one the researcher designed, and on H-Factory. ③ is
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
