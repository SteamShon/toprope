# Roadmap

Budget: ~10h+/week, evenings and weekends. Each milestone has a question, an exit
criterion, and a kill/pivot criterion. Dates are targets, not commitments.

| | Question | Target |
|---|---|---|
| M0 | Can we declare a decision and block a call with it? | 1 week |
| M1 | **H-Enforce / H-Propagate**: does the gate beat prose? | 3 weeks |
| M2 | **H-Author**: can history yield confirmable decisions that cut re-explanation? | 3 weeks |
| M3 | **H-Triage**: block / exception / amendment, read-back, `UNKNOWN` | 2–3 weeks |
| M4 | Generalize to a synthetic business domain; write-up; go public | 2–3 weeks |

---

## M0 — Skeleton (1 week)

Deliverables
- Pick implementation language (recommendation: Python + `uv`, because experiment analysis
  is in the same language; record as ADR).
- Decision schema v0 (`docs/decision-schema.md`) + JSON Schema validation.
- Core domain: `Decision`, `Verdict`, `AuditEvent`; ports: `DecisionStore`,
  `PolicyEvaluator`, `ActionSource`, `AuditLog`.
- Adapters: file-based store, built-in matcher evaluator, Claude Code `PreToolUse` hook
  adapter.
- 5 real decisions from the researcher's own work declared in `examples/decisions/`.

Exit: a declared decision blocks a matching tool call in a live Claude Code session, with
the reason returned to the agent and an audit event written.

Kill: none (engineering only). If hook semantics cannot express a needed block, record it.

## M1 — Enforcement experiment (3 weeks)

See [`experiments/M1-enforce.md`](experiments/M1-enforce.md).

Two tracks:
1. **Controlled**: task suite × 4 conditions (none / prose / gate / prose+gate) × repeated
   runs with headless agents. Includes a mid-run rule revision for H-Propagate.
2. **Dogfood**: run the gate on own daily work for 2 weeks. Log *off-declaration rate*
   (calls no decision spoke to), blocks, false blocks, overrides.

Exit: report with violation rates, completion, false-block rate, cost, and a stated verdict
on H-Enforce and H-Propagate.

Kill/pivot: if prose ≈ gate within noise on most tasks, reposition enforcement as a safety
boundary for irreversible actions only, and move the main research weight to M2 (authoring).

## M2 — Authoring from history (3 weeks)

- Parse own agent transcripts (Claude Code session JSONL; Codex logs if available).
- Extract candidate decisions from corrections, rejections, repeated instructions. Each
  candidate carries source quotes, proposed scope, and a one-off vs. standing guess.
- Small review CLI: accept / edit / reject / scope-to-this-repo / unsure. Accepted →
  declared decision feeding the M0 gate.
- Measure on subsequent real tasks: re-explanation count, corrections, confirmation time,
  candidate precision (share accepted), over-generalization incidents.

Exit: verdict on H-Author with numbers. Kill: if confirmation time exceeds re-explanation
saved over two weeks of use, narrow the extractor to one decision category.

## M3 — Lifecycle (2–3 weeks)

- Contradiction triage: a blocked call can be resolved as *block*, *exception (this once,
  with reason)*, or *amendment proposal (owner approval required)*.
- Exception counter per decision; threshold → amendment proposal.
- Withdrawal and supersession with version history; in-flight tasks see the version they
  started with unless stated otherwise.
- Read-back port: effects re-read where possible; timeouts recorded as `UNKNOWN`.
- Bypass audit: list execution paths the gate does not see.

Exit: verdict on H-Triage; documented guarantee boundary (RQ5).

## M4 — Generalization and release (2–3 weeks)

- Synthetic business domain behind an MCP tool (refund window or ad-budget reallocation),
  using the same core and a new `ActionSource` adapter.
- Check that swapping adapters keeps the same decisions with the same limits.
- Write-up: findings, negative results, claims we cannot make.
- Decide license (Apache-2.0 proposed) and make the repository public.

## Later (not planned)

- Thread C: response models / policy learning.
- Self-compile: modeling the authoring domain in Toprope itself.
- Harness² comparison: propose–probe–compose improvement vs. human-approved declarations.
- Durable runtime (Temporal / LangGraph) and host (OpenDots) adapters.
- Sharing expert decision packages.
