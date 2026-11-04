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
- Merge with a merge commit. Then tag `main` with `vX.Y.Z`.
- Releases are cut by the maintainer.

## Commits and PR titles

- The PR title becomes the squash commit message. Write it in the imperative, ≤ 72
  characters, e.g. `Add M1 self-compile gold-set template`.
- The PR description says what changed, why, and how it was checked.
- Keep PRs small: one concern per PR.

## Project conventions every PR follows

- **Name the link.** Toprope is organized around the claim chain (P0 premise → ① iterate
  safely → ② model is right → ③ works as built → ④ shared language → ⑤ evolves → ⑥ org productivity). Every PR, experiment
  doc and ADR states which link(s) it serves, or `none` for enablers.
- **Claim status changes only with a verdict.** The `Status` column of the README
  claim-status table changes only in a PR that reports a preregistered experiment verdict.
  The links and hypotheses themselves change only through an accepted ADR.
- **Decisions go into ADRs** (`docs/adr/`). Supersede an ADR when it changes; do not delete it.
- **Gold sets are human-only.** Gold scenarios, post-deploy probe suites, and seeded change
  lists (with their answer keys and bindings) are written by the researcher. Agents must not create or edit them. Verdict rules
  and thresholds may be *drafted* by an agent when the researcher asks. They are marked
  `draft` until the researcher reviews and freezes them in their own commit, before the
  experiment's checks are built.
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

## Repository settings (maintainer)

These cannot be enforced from the repository files. Set them in GitHub:

- Default branch: `develop`, so new PRs target it by default.
- Allowed merge methods: squash and merge commit. Disable rebase merging.
- Branch protection on `main` and `develop`: require a pull request, and block force
  pushes and deletion.
