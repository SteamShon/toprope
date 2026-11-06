# Contributing

Branching, merge methods, releases and project conventions are in [`AGENTS.md`](AGENTS.md).
It is the single source for both people and coding agents.

In short:
- Cut a branch from `develop` and open a PR with base `develop`.
- Normal PRs are squashed. Umbrella PRs and release PRs (`develop` → `main`) use a
  merge commit.
- Never push directly to `main` or `develop`.
- Name the claim-chain link your change serves.
- Update [`docs/STATUS.md`](docs/STATUS.md), or say why not in the PR description. CI checks it.
