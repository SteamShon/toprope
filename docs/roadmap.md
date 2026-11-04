# Roadmap

Link: all. Each milestone is defined by the link it gives a verdict on. Work can span
several links, but a milestone ends with a verdict. Budget is ~10h+/week. Dates are targets.

| Milestone | Link | Question | Target |
|---|---|---|---|
| M0 | none (enabler) | A minimal hand-built kernel that can compile a domain into MCP + UI | 2 weeks |
| M1 | ① ② (self) | Model Toprope's own authoring workflow by iterating; do compile-time checks catch what natural-language skills cannot? | 3–4 weeks |
| M2 | ① ② (dogfood) | Does the same hold on another domain, using the self-compiled tool? | 3 weeks |
| M3 | ③ | Do people and agents act on the same meaning through the capsule? | 3 weeks |
| M4 | ④ | Do logs, proposals and decisions make domains better through use? | 3 weeks |
| M5 | ⑤ (partial) | Do typed handoffs between domains preserve intent? Write-up, go public | 3 weeks |

If a link is weakened or refuted, later milestones are re-planned before they start. Then
the claim status in the README is updated.

---

## M0: Kernel (no claim, 2 weeks)

The bootstrap: the smallest hand-built kernel that later milestones can generate from.

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
- **Change-check pipeline v0 (ADR-0009)**, the core of the compiler: diff against the current
  version; structural and semantic-conflict checks; scenario regression; log replay; LLM
  natural-language conflict warnings; preview build. Done when an edit reaches a validated
  preview in minutes on the toy domain.
- Execution with precondition and role checks, plus an append-only event log.
- Source readers: repository, markdown records, session transcripts, interview log.

Exit: a small toy domain compiles to working MCP and UI, and calls are logged.
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

## M2: Dogfood domain (① ② replicated, 3 weeks)

Use the self-compiled authoring tool from M1, not the hand-built kernel, to model a
second, everyday domain. The candidate is the experiment lifecycle (hypothesis → design →
approval → launch → readout → ship/kill), sourced from an OSS experimentation platform
plus the researcher as owner. Same metrics and gold-set procedure as M1.

Phase B (the change sequence vs. a natural-language skill) is repeated on this domain.

Questions:
- Is the second domain cheaper than the first?
- Did the generated tool hold up, or did it need hand fixes?

Exit: verdicts on H-Iterate and H-Fidelity outside the self domain. This is the stronger
test, because the self domain is one the researcher designed.

## M3: Shared language (③, 3 weeks)

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

## M4: Evolution (④, 3 weeks)

- Record both kinds of decisions as first-class data: work decisions and domain-change
  decisions.
- Proposal engine: from logs and accumulated work decisions, propose model diffs with
  evidence. Humans decide in the generated UI. Accepted diffs regenerate the surfaces.
- Apply this to both domains, including the self domain, so the authoring tool improves
  itself. No self-approval, and the gold set and verdict checks stay outside the loop.

Exit: verdict on H-Evolve (proposal acceptance rate; accuracy and clarifications before and
after; over-generalization incidents).

## M5: Handoff and release (⑤ partial, 3 weeks)

- A typed handoff "experiment decided ship → delivery request" into a small third domain
  (code → product delivery), compared with a written note.
- State plainly what ⑤ needs that a personal project lacks: real teams and real handoffs.
- Write-up with findings, negative results and claims we cannot make. Choose a license
  (Apache-2.0 proposed) and make the repository public.

## Later

⑤ with real teams. Learning from accumulated work decisions. Real external effects with
read-back. Adapters for other runtimes and hosts (Temporal, OpenDots). Comparison with automated harness
improvement (Harness²).
