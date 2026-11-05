# M1 instruments: a guide for writing them

Link: ① iterate safely, ⑥ (partial); self-compile. Status: **draft by the assistant, at the
researcher's request; revised for ADR-0029, ADR-0030 and ADR-0031 (2026-11-05)**. It is a guide, not an
instrument: it holds **no questions, answers, probes, intents or key entries**. Those are
written by the researcher (AGENTS.md). The researcher may edit or discard this guide freely.

## What changed (ADR-0029, ADR-0030)
- **② is no longer judged in M1.** It moves to M2, on an application domain whose expert is
  not Toprope's builder. M1 judges ① (do compile-time checks catch the seeded problems?)
  and ⑥ (partial: does the handoff hold?), and reports self-compile as a feasibility result.
- **No gold set in M1** (ADR-0031). The self domains are confirmed by interview, the
  regeneration check, the probes and your sign-off. M1 freezes four files.
- **Authoring is a commit log** (ADR-0029): immutable commits, approval tags, a semantic
  diff, and Delivery pointing an environment at one commit. Write everything against this
  model. Nothing refers to version states such as stale, withdrawn or rejected.

## What stays sealed
- **`change-key.yaml` and its mix** are never shown to an agent. When an agent runs the
  validator for you, it uses `--sealed`.
- **This guide is not a Phase A source.** The source readers never read `experiments/`.
- The probe suite is not held-out evidence, so it may be drafted with an agent's help. You
  review it and commit it yourself.

## The self domains: built by interview, no gold set (ADR-0031)
Domain Authoring and Domain Delivery are planned and built in M1 Phase A through the staged
interview with you. Your confirmations, the regeneration check, the probes and your sign-off
at the switch-over confirm them. There is no gold set to write for M1. The gold template and
its validator stay for M2's application domain.

## The probe suite (`probe-suite.yaml`)
- **What a probe is.** A task given to an agent after a deploy, with a starting situation,
  the behaviors that **must** be observable, and those that **must not**. Observable means
  visible in the tool's outputs or the recorded history.
- **Candidate behaviors.** Agent behavior that a declaration cannot express, found while
  writing gold, is probe material:
  - drafting from the system first, then records, then the interview
  - redacting secrets and personal data, and never sending local-only sources
  - recording which sources were used
  - fetching a link once into a snapshot, and asking for a path when it is behind a login
  - asking conflicts first, bundling a stage's questions, ordering by priority, and
    stopping by the stop rule
  - collecting glossary terms as they come up
- **Careless-tool situations.** Add situations where a careless tool would go wrong:
  - finishing something only a person may finish
  - acting on a commit that is not the one reviewed
  - deploying an unapproved or superseded commit
- **Overlap.** No overlap with the domains' scenarios, and no reference to the change key.
- **Size.** About 8 to 12 per domain (a suggestion).

## Change requests (`change-requests.yaml`) and the key (`change-key.yaml`)
- **The commit model first.** Write every intent against the commit model. A request that
  targets something the model no longer has would become unbindable and silently shrink
  ①'s recall denominator. Rewrite or drop it, and every exclusion is reported in M1's
  results.
- **The intents.** About 20, in the order an owner would ask for them, as the owner would
  say them, each with a rationale. They are shown to every arm. Avoid "conflict", "break" or
  "seeded".
- **The key.** It holds about 6 conflicts, 4 breakages and 10 clean changes. Write it
  **alone**; never paste it into a chat. Include at least two problem types the checks were
  **not** designed for. Whether to seed handoff-breaking changes is your decision; keep it
  to yourself.

## Verdict rules (`verdict-rules.yaml`)
Start from `verdict-rules.template.yaml`, which holds the assistant's draft values, now
without ②. Review each threshold, including the latency targets, and set `status: frozen`
yourself.

## A plan
1. **About 30 min (agent help is fine):** the probe suite, including probes that check a
   handed-off request arrives intact (⑥).
2. **About 30 min, alone:** the change intents (against the commit model), then the key.
3. **About 15 min:** the verdict rules.
4. Validate, mark the files frozen, run `freeze`, and commit in your own commit, on a branch
   from `umbrella/m0a`:
   ```bash
   uv run --with pyyaml python experiments/tools/instruments.py validate experiments/m1/instruments
   uv run --with pyyaml python experiments/tools/instruments.py freeze experiments/m1/instruments
   ```
   Change-check work (M0a sub-PR 8) starts after this commit.
