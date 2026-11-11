# F1 measured again, after the change loop changed

Link: none (enabler: ADR-0049's program gives no link verdict). This is the plan for measuring F1
again, to check theme 1's targets as ADR-0053 §3–4 restates them. Progress is in
[`STATUS.md`](../STATUS.md).

## The window
- **From** theme 1's merge into `develop`: commit `3c041cbd` (#201), made 2026-11-11T02:45:09Z. Every
  self-domain change approved after it went through the new loop. Changes before it did not.
- **To** the time of the measure.
- The baseline (18.8 / 8.3 / 0.053, in [`U-theme1-change-loop.md`](U-theme1-change-loop.md)) covers
  the logs before theme 1. The two windows do not overlap, so they compare cleanly.

## When to measure
Measure once both of these hold, and again at M2's spec freeze:
- the window holds at least **five approved changes** to the self domains;
- at least **three of them are low risk**.

A smaller window gives a number, but the number does not stand for much. Until then the measure
is read as "not enough changes yet". It is not reported as a result.

## How
```bash
uv run python tools/usability_baseline.py --since-commit 3c041cbd \
    --record experiments/usability/f1-$(date -u +%Y-%m-%d).json
```
`--record` writes the measure, its window and the repository's HEAD to a new file. It refuses to
overwrite a recorded measure. Commit the file with a short note.

## Targets (ADR-0053 §3–4)

| Measure (tool output) | Baseline | Target |
|---|---|---|
| `person_touches.per_approved_change`, low-risk changes | 2.8 (all changes) | 1 |
| `approvals_per_approved_change_by_risk` | 1.5, risk not recorded | low: 1, high: 2 |
| `approval_runs_by_channel` | GitHub only | either channel counts as one approval |
| `refusals_per_command.refused_or_failed` | 0.053 | at most 0.026 (half) |
| `refusals_per_command.failed_before_the_gate_per_command_attempted` | not recorded | reported beside the rate, no target yet |

A target is **met** when the window meets the "when to measure" rule and the number is at or
better than the target. It is **not met** when the number is worse. Otherwise it is **open**.

## How to report it
- Add a row to the table below.
- Change the U row in `STATUS.md`. Its status turns ✅ only when F1 and F2 are both met.
- Name the record file.

| Date | Window | Approved changes (low / high) | Touches, low risk | Approvals, low / high | Refused or failed per command | Record |
|---|---|---|---|---|---|---|
| 2026-11-11 | from `3c041cbd` | 0 (0 / 0) | — | — | — | none: no change since the merge |

## What it cannot tell
- **Only the self domains.** F1 counts their logs only. A team's own domain is F2's job.
- **Failed request runs** are recorded since #238; runs before that were not. The tool reports
  commands that may be steps of an unrecorded failed run beside the touches.
- **A change approved in one window and shipped in the next** counts in the window of its approval.
