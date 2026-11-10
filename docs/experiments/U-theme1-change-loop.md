# Theme 1: the change loop (ADR-0049)

Link: none (enabler for ① and ⑥). The plan for `umbrella/usability-change-loop`: what it
changes, in which order, and the targets it is measured against. Progress is in
[`STATUS.md`](../STATUS.md).

## Targets
Measured with `tools/usability_baseline.py` (F1) against the baseline in STATUS:

| Measure | Baseline | Target |
|---|---|---|
| commands by a person or an agent, per approved change | 18.8 | the loop's own run: one `toprope change` and one approval |
| commands by a person, per approved change | 8.3 | kept for comparison; the target is the next row |
| a person's touches, per approved change | 2.8 (computed later on the same logs, below) | 1 for a low-risk change (one approval), otherwise at most 3 |
| approvals, per approved change, by risk | 1.5, risk not recorded before ADR-0050 | low: 1; high: 2 (ADR-0050) |
| refusals and failed effects, per command by a person or an agent | 0.053 | at most half the baseline (ADR-0049, 5) |
| options on every command | 4 (`--composition --kernel-root --workspace --env`), plus `--member` | 0 |
| errors without a fix | not counted | 0, enforced by a test |
| failures before the gate | not recorded | recorded, then measured again |

## How F1 is computed
`uv run python tools/usability_baseline.py [--since DATE] [--until DATE] [--json]`. All counts are
over the window: from `--since` (included) up to `--until` (not included); a date without a time
is midnight UTC. With neither, the window is everything the logs hold, which is how the baseline
was recorded, so `uv run python tools/usability_baseline.py --until 2026-11-09` on the logs of
2026-11-09 reproduces it.

What has a time: a kernel command takes the time of the events it appended (`at` in its outcome
in `idempotency.jsonl`); a command that appended none (a refusal) takes the time of the command
before it in the same log, and has no time if no command before it has one (it is then counted
only when the window is open at both ends). A failed effect, an approved human request (`approval-runs.jsonl`), a
failure before the gate (`.toprope/failures/`) and a commit (`log.jsonl`) carry their own `at`.
A log line that does not parse stops the tool with its file, its line and the fix.

- **Approved change**: a successful `approve_commit` by a person in the window, in any domain.
- **Commands by a person or an agent, per approved change**: kernel commands in the window by an
  actor the events name as a person or an agent (or one they do not name), over approved
  changes. The kernel's replies (`external:`, `handoff:`) are left out.
- **Commands by a person, per approved change**: the same, by a person only. A human request's
  steps run as the person (ADR-0039), so one approved request of nine steps counts nine here.
- **A person's touches, per approved change** (the target's measure): approved human requests in
  the window that take at least one `run` step, plus kernel commands by a person in the window
  that no approved request's run took, over approved changes. A run's commands are found from
  its record, over the whole log (not only the window): its `run` steps are matched in their
  order, each to the earliest successful command not yet matched, by the person the run acted as
  (`as`), with the step's action and target, after the step before it, at or before the record's
  `at`, after the record before it, and no more than 20 minutes before the record (the `act`
  job's timeout; the steps and `record` run in that one job). `$commit` is the commit the matched
  `commit_draft` made: the target of the kernel's `record_commit` reply after it in the log. A run
  is placed in the window at the time of its `approve_commit` command, so a change and the run
  that approves it fall in the same window and an edge inside a run neither splits it nor counts
  its steps as typed; a run that approves nothing is placed at its first command. Steps not found
  are reported (`request_steps_not_found`); requests with only instrument steps (`freeze`,
  `amend`) are reported apart and not counted, as they are not part of a change.
- **Failed request runs.** A run that fails is not recorded in `approval-runs.jsonl` today, so its
  steps that ran count as commands typed by the person, and the approval is not counted.
  `possibly_failed_request_steps` reports how many of the commands outside a request have the
  action and target of a step of a run recorded within 60 minutes after them; they stay counted.
  A failed run is recorded with `ran` and `failed`: it counts as one approval, and its first `ran`
  steps are looked for (a step whose action was taken but whose follow-up failed is among them),
  then the step it stopped at (`failed.step`, its position in the run's own `steps`; a rest of an
  earlier request has its own steps), matched to a command that did not succeed, so a refusal the
  run met is not counted as typed by the person. Not finding it is not a missing step: the step
  may have failed before the gate.
- **Approvals per approved change, by risk**: for each approved change, the approved requests in
  the window whose found commands approve it (`approve_commit`) or ship it (`deliver`, `preview`,
  `deploy`, `run_probes`, `verify` on it), plus `approve_commit` commands on it a person typed
  outside a request. Grouped by the risk `check_commit` last recorded on the commit at or before
  its approval (`risk` in `checks.jsonl`, ADR-0050; a later re-check does not change it); `unknown` where none was recorded (every change before
  ADR-0050). A high-risk change whose second approval falls after the window shows one.
- **Refusals and failed effects, per command** (`refusals_per_command.refused_or_failed`, also
  `refused_or_failed_per_command`): refusals at the gate of commands by a person or an agent,
  plus `EffectFailed` events, over the same commands.
- **Failures before the gate, per command attempted**: records under `.toprope/failures/` in the
  window, over those commands plus the failures (a failure never reached the kernel, so it is an
  attempt the command log does not hold). It is reported beside the refusal rate, never added to
  it.

**What "comparable" means.** A before/after comparison uses the same measure, computed the same
way, on two windows that do not overlap. Refusals and failed effects per command are comparable
between the baseline and any later window: both come from the gate's own logs. Failures before
the gate were not recorded before D1b (#204), so the baseline has no such number and no sum of
the two that could be compared; ADR-0049 (5)'s target for refusals applies to
`refused_or_failed`, and failures before the gate are reported beside it, compared only between
windows that both start after D1b. A person's touches and approvals by risk were not part of the
recorded baseline; computed on the same logs and window they are 2.8 touches per approved change
(5 approved requests + 12 commands outside one, for 6 changes) and 1.5 approvals per change, risk
unknown. They are given for orientation, not as recorded baseline numbers.

**The re-measure.** After theme 1 merges into `develop`, F1 is measured with `--since` set to the
time of the first change made with the new loop (after the M1 recheck's batch, which would
otherwise be counted), and `--until` left open or set to the measurement's date. The command and
the window go in STATUS next to the numbers.

## Sub-PRs, in order

| # | Item | Runs the self domains' loop? |
|---|---|---|
| 1 | C3: `toprope.yaml`, and the member found from the action | no |
| 2 | D1a: an error catalog, and a test that every error in the loop's path (CLI, kernel services, workspace, commits) names its fix | no |
| 3 | D1b: a failed command is recorded, so F1 sees failures before the gate | no (a new log; the self domains' logs keep their format) |
| 4 | B4: a citation by quote or query resolves to a chunk when exactly one matches | no |
| 5 | B5: one readable diff to confirm a change, from the semantic diff | no |
| 6 | C1: `toprope change "<intent>"`: propose, commit and check, leaving one request for a person | no to build; yes to try on the self domains |
| 7 | C2: approvals by risk, its own ADR first; then built | yes |

A sub-PR that runs the self domains' loop waits until no other open PR changes their commit
store or logs (AGENTS.md, "Self domains: one loop at a time").

## Done when
Every row above is done, F1 is measured again on a change made with the new loop, and the
targets are met or the gap is reported in the umbrella's PR.
