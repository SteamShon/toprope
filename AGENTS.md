# Working in this repository

This is the single source of working conventions for people and coding agents
(Claude Code, Codex, and others). `CLAUDE.md` and `CONTRIBUTING.md` point here.
If a convention changes, change it here.

## Branches

| Branch | Purpose | Who writes to it |
|---|---|---|
| `main` | Released state only | Release PRs from `develop` only |
| `develop` | Integration branch; the base for all work | PRs only |
| work branches | One change each, cut from `develop` | You |

Never commit or push directly to `main` or `develop`. Never force-push to them.

Work branch names: `<type>/<short-kebab-description>`.

| Type | Use for |
|---|---|
| `feat/` | new capability |
| `fix/` | bug fix |
| `docs/` | documents, ADRs, notes |
| `exp/` | experiment setup, runs, analysis |
| `refactor/` | behavior-preserving change |
| `chore/` | tooling, CI, dependencies |
| `umbrella/` | a larger change assembled from several sub-PRs (see below) |

## Flow

```
develop ──► feat/x ──PR (squash)──► develop
develop ──► umbrella/y ◄─PR (squash)── feat/y-part-1, feat/y-part-2
            umbrella/y ──PR (merge commit)──► develop
develop ──release PR (merge commit)──► main
```

1. Start from the latest `develop`:
   `git fetch origin develop && git switch -c <type>/<name> origin/develop`
2. Keep the branch current by rebasing onto or merging `origin/develop`. Rebase only your
   own, unshared branch.
3. Open a PR with **base `develop`**. Set the base explicitly, because the GitHub default
   branch may differ.
4. Merge according to the table below.

## Merge methods

| PR | Base | Method |
|---|---|---|
| Normal work PR | `develop` | **Squash and merge** (default) |
| Sub-PR into an umbrella branch | `umbrella/*` | Squash and merge |
| Umbrella PR | `develop` | **Create a merge commit**, which keeps each sub-PR's squashed commit |
| Release PR | `main` | **Create a merge commit**. Never squash or rebase a release. |

Rebase-merge is not used.

### Umbrella PRs

Use an umbrella when one logical change is too large to review as one PR but should land
on `develop` all at once (for example, a milestone's kernel). Create `umbrella/<name>` from
`develop` and open its PR to `develop` early as a draft. Then send sub-PRs into the
umbrella branch. Merge the umbrella with a merge commit once all sub-PRs are in and the
umbrella is up to date with `develop`.

### Releases

- A release PR has head `develop`, base `main`, and the title `Release vX.Y.Z` (or
  `Release <milestone>`, e.g. `Release M1`).
- Its description lists the merged PRs and any change to the claim-status table.
- Before it, a cleanup PR into `develop` trims `docs/STATUS.md` (see Progress) and sets
  `Cleaned for release: <name>`. The release PR's check fails until that name matches.
- Merge with a merge commit. Then tag `main` with `vX.Y.Z`.
- Releases are cut by the maintainer.

## Commits and PR titles

- The PR title becomes the squash commit message. Write it in the imperative, ≤ 72
  characters, e.g. `Add M1 self-compile gold-set template`.
- The PR description says what changed, why, and how it was checked.
- Keep PRs small: one concern per PR.

## Progress: `docs/STATUS.md`

[`docs/STATUS.md`](docs/STATUS.md) is the one place that says what is done and what is left.
It is a snapshot, not a log: history stays in git, PRs and ADRs, and plans stay in the
roadmap and the milestone and experiment docs. Other documents do not restate the current
state; they link here. The README claim-status table stays in the README, because its
`Status` column follows the verdict rule above.

- **Its shape.** A *Summary* table with one row per milestone (✅ done, 🟡 in part, ⬜ not
  started); a section per active milestone with an item table (item, status, PRs) and short
  notes on how things work now; *Next*, numbered; *Left from reviews*; *Open questions*.
- **Every PR into `develop` or an `umbrella/*` branch fixes any line it makes untrue**: an item
  added, a status changed, its PR number filled in, a review leftover resolved (delete it),
  and `Updated:` changed. A PR that changes nothing there says so in its description with a
  line `STATUS.md: no change - <reason>`.
- **Review leftovers.** What a review defers ("later", or a finding reported as skipped) goes
  under *Left from reviews* with the PR and the review date, in the commit that addresses the
  review. Leftovers from a PR's last review round go in the next PR that changes STATUS.md;
  do not change a PR's head for that alone.
- **CI enforces this.** `.github/workflows/status.yml` runs `tools/status_check.py` on every
  PR. It also checks that the file keeps its sections: Summary, Next, Left from reviews,
  Open questions.
- **Each release trims it.** In the cleanup PR before a release: collapse what the release
  ships (the release PR description lists it) into one line per milestone, remove anything no
  longer true, handle review leftovers older than one release (resolve, keep with a reason,
  or drop), and set `Cleaned for release: <name>`.

## Project conventions every PR follows

- **Name the link.** Toprope is organized around the claim chain (P0 premise → ① iterate
  safely → ② model is right → ③ works as built → ④ shared language → ⑤ evolves → ⑥ org productivity). Every PR, experiment
  doc and ADR states which link(s) it serves, or `none` for enablers.
- **Claim status changes only with a verdict.** The `Status` column of the README
  claim-status table changes only in a PR that reports a preregistered experiment verdict.
  The links and hypotheses themselves change only through an accepted ADR.
- **Decisions go into ADRs** (`docs/adr/`). Supersede an ADR when it changes; do not delete it.
- **Gold sets are human-only.** Gold scenarios, post-deploy probe suites, and seeded change
  lists (with their answer keys and bindings) are written by the researcher. Agents must not
  create or edit their **content**: questions, answers, probes, intents, key entries,
  bindings. Verdict rules and thresholds may be *drafted* by an agent when the researcher
  asks. They are marked `draft` until the researcher reviews and freezes them in their own
  commit, before the experiment's checks are built.
- **Exception: the self domains' M1 instruments** (ADR-0034, ADR-0038). M1 gives no link
  verdict, so its probe suite, change requests, change key, verdict rules and binding may be
  drafted by an agent when the researcher asks, including multiple-choice options the
  researcher selects from.
  The researcher selects, reviews and freezes them in their own commit, before the pilot
  runs. Everything that feeds a link verdict (M2 and later instruments, any gold set) stays
  human-only.
- **Freezing and amending.** The researcher freezes an instrument, or tells an agent to, and
  the commit records that instruction. From a cloud session, the agent writes the steps as a
  human request (`.toprope/requests/<id>.yaml`) and the researcher approves its run in GitHub;
  the commit records the approver and the run (ADR-0039). A frozen file may change later only through
  `instruments.py amend --reason`, which keeps the old hash and the reason in `FROZEN.json`;
  results report which version each run used. An agent amends only at the researcher's
  explicit instruction.
- **Format changes on request.** When the researcher asks, an agent may change the
  **format** of these instruments: the templates' fields and comments, the validator, and
  the guides. Such a change writes no content, never touches a filled or frozen instrument
  file, and never reads a sealed one (a change key, or held-out items). The PR says it was
  requested.
- **Language.** Docs are in English. Working notes in `notes/ko/` may be in Korean.

## Rules for coding agents

- Before starting, cut a work branch from `origin/develop`. If you are given a session
  branch, base it on `origin/develop`, and target your PR at `develop`.
- Never push to `main` or `develop`, and never open a PR into `main` unless the
  maintainer asks for a release PR.
- Do not merge PRs unless the maintainer asks. When asked, use the merge method from the
  table above.
- Do not change the claim-status table, ADR decisions or gold sets on your own initiative.
  Propose them in the PR description instead.
- Do not put model identifiers in commits, PRs or code.
- Update `docs/STATUS.md` in the same PR as the work it describes (see Progress).
- **Real tests only.** A new test must fail against the code before your change (or cover
  behavior the change adds). Never write a test that already passes against the old code
  and call it coverage. Never skip, delete, `xfail`, comment out or weaken a test, or loosen
  an assertion, to get green: fix the code, or stop and explain. This applies equally to
  generated harnesses and to the M1 instruments.

## Development

- `uv sync`, then `uv run pytest`.
- PostgreSQL tests run when `TOPROPE_PG_DSN` is set (e.g. `host=127.0.0.1 port=5432
  user=postgres dbname=postgres`); each test uses its own throwaway schema. Without it, the
  same contract tests run on the memory and SQLite stores only.

## Repository settings (maintainer)

These cannot be enforced from the repository files. Set them in GitHub:

- Default branch: `develop`, so new PRs target it by default.
- Allowed merge methods: squash and merge commit. Disable rebase merging.
- Branch protection on `main` and `develop`: require a pull request, and block force
  pushes and deletion.
- Automatically delete head branches: on, so a work branch is removed when its PR
  merges. `develop` is safe as the default branch; a deleted branch can be restored from
  its merged PR.
- Required status check: add `status` (from `.github/workflows/status.yml`) to the ruleset
  on `main` and `develop`, so a PR cannot merge while `docs/STATUS.md` is stale.
