# Research Charter

Version 0.1 — 2026-11-04

## 1. Problem

People who use coding/work agents seriously accumulate a large amount of decided
knowledge: preferred tools, forbidden actions, approval boundaries, completion criteria,
corrected assumptions, rejected proposals. Three things go wrong with it.

1. **It is not enforced.** A rule in `CLAUDE.md` is a request. The agent may read it,
   forget it in a long task, or trade it off against the easiest path. A sentence that
   says "do not do X" and an execution path on which X cannot happen are different things.
2. **It is copied, not declared.** The same decision is restated in several prompts,
   files and tools. When it changes, every copy must be found and edited (an update
   anomaly in the Codd sense). Consumers × copies = N × M maintenance.
3. **It is not authored.** Most decisions are made implicitly — by correcting the agent,
   rejecting a proposal, choosing one option. They stay buried in transcripts. The person
   pays again by re-explaining.

## 2. Scope (first year)

The research joins two of the three threads from prior work (see `lineage.md`):

| Thread | In scope? |
|---|---|
| **A. Enforcement** — approved decisions gate calls on the execution path | **Yes (M1 first)** |
| **B. Authoring lifecycle** — candidates from work history, approval, exception, revision, withdrawal | **Yes (M2–M3)** |
| C. Response-model learning — which allowed action yields better outcomes | No. Long-term. Needs traffic and outcome data a personal project lacks. |

**First domain: the researcher's own coding-agent work (dogfooding).** The execution path
already exists (agent hooks such as Claude Code `PreToolUse`), the history already exists
(session transcripts), and the user being studied is the researcher. After the loop holds
there, one synthetic business domain (e.g. refunds or ad-budget changes behind an MCP tool)
tests whether it generalizes beyond coding.

## 3. Research questions

- **RQ1 (Enforce).** Does putting an approved decision on the execution path reduce
  violations compared with stating it in context, at what cost in task completion,
  turns, and false blocks?
- **RQ2 (Propagate).** When a decision is revised, does a single declared source keep all
  consumers consistent where prose copies drift?
- **RQ3 (Author).** Can decision candidates mined from an agent user's own history, then
  confirmed by the user, reduce re-explanation and corrections in later tasks, without
  promoting one-off choices into rules?
- **RQ4 (Lifecycle).** Does triaging contradictions into *block / exception / amendment*,
  and surfacing accumulated exceptions as amendment proposals, keep rules current with
  less human effort than editing prose?
- **RQ5 (Boundary).** Which parts of a decision can be checked mechanically and which must
  remain judgment? Where does the gate's guarantee end (bypass paths, timeouts, unknown
  effects)?

## 4. Hypotheses and what would weaken them

| ID | Hypothesis | Weakened if |
|---|---|---|
| H-Enforce | Gate enforcement lowers violations vs. a `CLAUDE.md` baseline with equal information. | Prose-only violation rate is within noise of gated, or gating costs more completion than it saves. Then enforcement narrows to a safety boundary for irreversible actions. |
| H-Propagate | A declared decision keeps consumers consistent after revision; prose copies drift. | Agents reliably pick up revised prose with no stale behavior. |
| H-Author | Mined + confirmed candidates reduce re-explanation in subsequent tasks. | Confirmation burden ≥ re-explanation saved, or most candidates are one-off noise. |
| H-Triage | Exception accumulation is a useful amendment signal. | Exceptions are rare or random, or amendments proposed from them are mostly rejected. |

Each hypothesis is tested separately. Success of one does not imply another.

## 5. Distinctions kept throughout

- Knowing a method ≠ adopting it as default ≠ being authorized to act now.
- A rule being enforced ≠ the rule being correct.
- A tool returning success ≠ the effect having happened. Timeouts are `UNKNOWN`, not success.
- Reading a definition and proposing a change ≠ approving that change. No self-approval.
- Model improvement and explicit enforcement are compared, never assumed to substitute.

## 6. Non-goals

- A general agent framework, a hosted multi-tenant gate, or a marketplace.
- Choosing a durable runtime (Temporal, LangGraph) or host (OpenDots) before a milestone
  needs one. They remain candidates behind ports.
- Monetization as a success criterion.
- Reproducing any prior employer's code, specs, or data.

## 7. Evaluation principles

- Same model, tools and information across conditions; only the treatment differs.
- Include adversarial pressure: tasks where the rule conflicts with the shortest path.
- Count human cost: authoring, confirming, maintaining, reviewing — not only model tokens.
- Report negative results and the claims we can no longer make.
