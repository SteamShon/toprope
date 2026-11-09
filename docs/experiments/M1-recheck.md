# M1 recheck: the improved Toprope on M1's change list

Link: ① (pilot, no verdict; ADR-0034), ⑥. Status: **preregistered** (2026-11-09, decided by
SteamShon: "M1을 확신 수준 높여서 끝내고 M2로 넘어가고 싶다"; options drafted by the assistant).
Umbrella: `umbrella/m1-recheck`.

## Why

M1 was reported ([`M1-report.md`](M1-report.md)), and its findings were built (ADR-0048, the
M1-findings umbrella). Two things were left that keep M1 from being closed with confidence:

- **The probes measured themselves.** Several failed before any change in every arm
  ([`probe-baseline-findings.md`](../../experiments/m1/probe-baseline-findings.md)).
- **The new checks never ran end to end** on a real pair of domains: outcome rules, the
  capability diff, grouped findings, the natural-language check, the patch editor.

The recheck closes both before M2 starts, so that M2 does not come back to change M1.

## What it is not

**It gives no performance result.** ADR-0048 §6: the assistant that wrote the new checks has
seen M1's key, and the change list is the same. Any recall or precision it yields is biased
upward and is reported as a reference only. Whether the new checks help is M2's question, on a
change list someone else writes.

## What changes, and what stays

| Changes | Stays |
|---|---|
| The self domains adopt outcome rules, **promoted mechanically** from the person-only and role requirements their actions already carry (no new judgment, so no knowledge of the key enters them); the researcher approves the commits | The change requests, the sealed key and its binding |
| The baseline moves to the first approved commits with those rules; all four arms are rerun from it: NL, structured, Toprope, combined (the NL and structured materials are rendered again from the new declarations) | The run protocol (`instruments/run-protocol.md`): 5 reviews, 3 probe runs, blind grading, the decision log |
| The probe suite is amended through `instruments.py amend` (proposals of `probe-baseline-findings.md`, all adopted): P05 and P07 judged on what the agent did; examples of a pass and a fail for P01, P04, P08 | The grader prompt and model, the reviewer prompts |
| Each probe runs under a grant that covers its task, the same task power in every arm | The Remote Control runbook (ADR-0047) |
| The leftovers of #179 and of Phase B's harness are fixed | |

## Exit criteria (M1 is closed when all three hold)

1. **Probe gate.** Before any change (`seq: 0`), every probe passes at least 2 of its 3 runs in
   every arm. A probe that still fails the gate is dropped from M1's "found after deploy" with
   its cause recorded, and goes to M2's probe design as is; it is not amended a second time.
   Only causes in the probe or the world count for that: a failure the harness caused is fixed
   and the probe run again.
2. **A clean pipeline.** Every planned run completes: no world left incomplete, no flag lost in
   the recheck of the Toprope arm, every grade in JSON (after the retry), and `phase_b status`
   lists nothing stale. *Left from reviews* in `docs/STATUS.md` holds no item from M1, #179 or
   this umbrella.
3. **The grader's noise, measured.** The combined run is graded twice, in separate sittings. Each
   arm's recall differs by at most 0.1 between the two. Both gradings are reported; if the
   difference is larger, the researcher grades the disagreeing labels and that grade counts.

**Reported for reference only** (not a criterion): recall, grouped precision and found-after-deploy
per arm, next to M1's.

## Order

1. This preregistration.
2. The #179 leftovers: the `check` form of `requires`, an agent actor in the harness world, rules in
   the generated guide, the interview stage that asks for rules.
3. Mechanical promotion: a command that proposes outcome rules from per-action requirements.
   Other leftovers: Authoring's `record_questions` and its `params.questions`, the Phase B log's
   header, the stale folders in `phase_b status`.
4. The probes: the per-probe grants, the amended suite (a human request the researcher approves),
   and the gate in the scorer.
5. The self domains adopt the promoted rules (the researcher approves); the baseline moves; the
   local session reruns Phase B (ADR-0047); the researcher grades.
6. The recheck report, appended to `M1-report.md`; then M1 is closed in `docs/STATUS.md`.
