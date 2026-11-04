# Roadmap

Budget: ~10h+/week. The milestones follow the claim chain in the charter (§3): each one
tests one link, and later links use what earlier ones produce. Dates are targets.

| | Claim tested | Target |
|---|---|---|
| M0 | Skeleton: schema, compiler to MCP/UI, source readers, S1 pilot | 2 weeks |
| M1 | **① can be built + ② the model is right** (H-Author, H-Fidelity) | 3 weeks |
| M2 | **③ shared language** (H-Shared) | 3 weeks |
| M3 | **④ evolves through use** (H-Evolve) | 3 weeks |
| M4 | Second domain + handoff (toward ⑤), write-up, go public | 3 weeks |

---

## M0: Skeleton and S1 pilot (2 weeks)

- Decide the implementation language and record an ADR. Proposal: TypeScript for the core
  and generators, Python for analysis.
- Domain schema v0 with provenance and status on every element (`docs/domain-schema.md`).
- Compiler v0: domain → MCP (read tools, plus one tool per action with preconditions
  checked) and a minimal schema-driven UI (enough for S4 use).
- Source readers: repository (code, schema), records (markdown docs, issues export), and an
  interview session log.
- Choose the source system (GrowthBook candidate: check license and feasibility).
- Write and freeze the scenario gold set. Do the baseline hand-authored slice.
- **S1 pilot**: agent drafts from the system alone and is scored on held-out scenarios.

Exit: a drafted model compiles to working MCP/UI, and the pilot gate in M1 passes.

## M1: Authoring pipeline (3 weeks)

See [`experiments/M1-authoring.md`](experiments/M1-authoring.md). Stages S1 system → S2 records
→ S3 interview → S4 use, measured per stage, followed by three change requests.

Exit: verdicts on H-Author and H-Fidelity, and per-stage contribution.

Kill/pivot: if human time is mostly spent fixing agent drafts, narrow the scope. Agents
then draft only some element types (for example, actions and preconditions), and humans
author the rest. Record what agents can and cannot draft.

## M2: Shared language (3 weeks)

See [`experiments/M2-shared-language.md`](experiments/M2-shared-language.md). On the model M1
produced: docs plus generic tools / hand-written typed tools / capsule-generated MCP, with
intent errors as the primary metric, a pilot gate and a revision probe. The gold scenarios
from M1 are reused as tasks.

Exit: verdict on H-Shared. Kill/pivot as stated in the experiment doc.

## M3: Evolution through use (3 weeks)

- Both decision kinds are recorded as first-class data:
  - **work decisions** (approve, ship, kill, exception) with inputs and rationale
  - **domain-change decisions** (accept/reject a proposed model diff) with evidence
- Proposal engine: from logs (blocked calls, repeated clarifications, exceptions,
  overrides, patterns in work decisions) propose model diffs with evidence.
- Review in the UI. Accepted diffs create a new version and regenerate the surfaces.
- Measure: proposal acceptance rate, scenario accuracy and clarifications before and after,
  and over-generalization incidents.

Exit: verdict on H-Evolve.

## M4: Second domain, handoff, release (3 weeks)

- Run the M1 pipeline on code → product delivery. Did it get cheaper the second time? Was
  any core change needed?
- A typed handoff (experiment decided "ship" → delivery request) compared with a written note.
- Write-up: findings, negative results, claims we cannot make.
- License (Apache-2.0 proposed). Make the repository public (ADR-0005).

## Later (not planned)

- ⑤ organizational productivity with real teams.
- Learning from accumulated work decisions (thread C).
- Self-compile: model the authoring pipeline itself as a domain.
- Real external effects with read-back and `UNKNOWN`. Durable runtime and host adapters.
