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

## ADR-0034: M1 is a pilot, and agents may help
M1 gives no link verdict: ① and ⑥ are piloted here and judged in M2. So the self domains'
instruments may be drafted with an agent, including **multiple-choice options you select
from**: the probes, the change requests, the key and the verdict rules. You select,
review and freeze them in your own commit. Freeze the probe suite and the verdict rules
before the change checks are built, and the change requests and key before the pilot runs.

## What stays sealed
- **In M2 and later**, `change-key.yaml` and its mix are never shown to an agent. In M1 the
  key may be drafted with an agent (ADR-0034). When an agent runs the validator for you, it
  still uses `--sealed` by default.
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
- **The key.** It holds about 6 conflicts, 4 breakages and 10 clean changes. In M1 it may be
  drafted with an agent by multiple choice (ADR-0034); in M2 write it alone. Include at least two problem types the checks were
  **not** designed for. Whether to seed handoff-breaking changes is your decision; keep it
  to yourself.

### A menu of change types (requested by the researcher, 2026-11-05)
To write the intents mostly by choosing, pick a type from this menu, then write in one line
what that type means in the self domains, as the owner would say it, with a rationale. The
menu is generic: it names no element and no seeded problem. Tick types until there are
about 20 intents; a type may be used more than once.

| # | Type | Example in a bakery-order domain (not ours) |
|---|---|---|
| 1 | Add a step between two existing steps | "Put a tasting step before a wedding cake goes to production." |
| 2 | Split one action into two | "Separate taking a deposit from confirming the order." |
| 3 | Merge two actions or steps into one | "Packing and labelling can be one step." |
| 4 | Narrow who may do something | "Only the manager may cancel a paid order." |
| 5 | Widen who may do something | "Let part-timers mark an order as picked up." |
| 6 | Add a condition before an action | "No production before the deposit is paid." |
| 7 | Relax or remove a condition | "Small orders no longer need a deposit." |
| 8 | Change who approves, or add an approval | "Custom designs need the head baker's sign-off." |
| 9 | Add a required piece of information | "Every order records an allergy note." |
| 10 | Remove a piece of information, a step or an option | "We no longer offer same-day delivery." |
| 11 | Rename or redefine a term | "Call it a 'collection slot', not a 'pickup time'." |
| 12 | Change a deadline, a timer or an order of events | "Cancellations close 48 hours before pickup, not 24." |
| 13 | Add a new kind of thing or a new role | "Add catering orders, handled by an events lead." |
| 14 | Change what one domain hands to the other | "The kitchen also needs the delivery address." |
| 15 | Change what happens to things already in progress | "Orders already in production keep the old price." |

- **Write in the owner's words.** The menu's type names are for you; the intent does not
  use them, and names no element.
- **Go outside the menu at least twice.** The assistant wrote this menu, so its types are
  ones the assistant knows. At least two seeded problems should come from types not on it,
  so that some are ones the checks were not designed for (`designed_for_checks: no`).
- **The key stays yours.** Which intents are seeded, and how, goes only into
  `change-key.yaml`, written alone.

## Verdict rules (`verdict-rules.yaml`)
Start from `verdict-rules.template.yaml`, which holds the assistant's draft values, now
without ②. Review each threshold, including the latency targets, and set `status: frozen`
yourself.

## A plan
1. **About 30 min (agent help is fine):** the probe suite, including probes that check a
   handed-off request arrives intact (⑥).
2. **About 30 min (agent help is fine in M1, ADR-0034):** the change intents (against the
   commit model), then the key.
3. **About 15 min:** the verdict rules.
4. Validate, mark the files frozen, run `freeze`, and commit in your own commit, on a branch
   from `umbrella/m0a`:
   ```bash
   uv run --with pyyaml python experiments/tools/instruments.py validate experiments/m1/instruments
   uv run --with pyyaml python experiments/tools/instruments.py freeze experiments/m1/instruments
   ```
   `freeze` freezes whichever of the four files exist with `status: frozen`, so the probe
   suite and the verdict rules can be frozen first. Change-check work (M0a sub-PR 8) starts
   once those two are frozen; run `freeze` again for the change requests and key before the
   pilot runs (ADR-0034).
5. **Changing a frozen file later.** Edit it (keep `status: frozen`), then record the change
   with its reason; the old version stays in `FROZEN.json`, and results report which
   version each run used:
   ```bash
   uv run --with pyyaml python experiments/tools/instruments.py amend experiments/m1/instruments verdict-rules --reason "why"
   ```
