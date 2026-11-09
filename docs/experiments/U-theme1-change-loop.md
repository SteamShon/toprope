# Theme 1: the change loop (ADR-0049)

Link: none (enabler for ① and ⑥). The plan for `umbrella/usability-change-loop`: what it
changes, in which order, and the targets it is measured against. Progress is in
[`STATUS.md`](../STATUS.md).

## Targets
Measured with `tools/usability_baseline.py` (F1) against the baseline in STATUS:

| Measure | Baseline | Target |
|---|---|---|
| commands by a person or an agent, per approved change | 18.8 | the loop's own run: one `toprope change` and one approval |
| commands by a person, per approved change | 8.3 | 1 for a low-risk change (needs C2's ADR), otherwise at most 3 |
| options on every command | 4 (`--composition --kernel-root --workspace --env`), plus `--member` | 0 |
| errors without a fix | not counted | 0, enforced by a test |
| failures before the gate | not recorded | recorded, then measured again |

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
