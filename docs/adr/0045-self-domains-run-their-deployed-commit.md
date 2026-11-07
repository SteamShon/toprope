# ADR-0045: The self domains run their deployed commit

- Link: ③ works as built, ① iterate safely · Status: accepted · 2026-11-07 · decided by:
  SteamShon (the recommendation; drafted by the assistant)
- Builds on: ADR-0029 (commits and the deploy floor), ADR-0037 (the self domains run from their
  declarations), ADR-0042 (which rule decided an event)

## Context
`toprope-run --composition` and `toprope-server --composition` read each member's working-copy
declaration (`domains/<domain>/<domain>.domain.yaml`). For the self domains, two things follow:
- A change takes effect when it is written to the file, before anyone confirms, approves or
  deploys it. The change check, TLC's check in the approval (ADR-0044) and the probes before
  `verify` (#147) all guard a commit that is not what runs.
- Every event carries `domain_version` 1, so it cannot say which approved commit decided it.
  ADR-0042 lists the self domains as the exception to "which rule decided an event".

A domain served from an environment (`toprope-server` from a build) already runs an approved
commit. The self domains' environment, though, is rebuilt in every approval run (ADR-0039), so
what it records does not last.

## Decision
1. **Deploying records the commit with the commits.** Each successful `deploy_commit` appends
   the commit and the environment to `.toprope/commits/<domain>/deployments.jsonl`. This file
   is kept in git, append-only like the other commit-store files.
2. **A member runs its deployed commit, else its approved `main`.** With `--kernel-root`, the
   commands load each member from that commit, with `version` set to the commit's sequence
   number. Events then record it as `domain_version`. A member with neither runs from its file.
   `--working-copy` asks for the files explicitly.
3. **Each command loads afresh.** In a human request, the steps after a `deploy` run the new
   commit; the steps before it run the old one. A Delivery change is delivered, previewed and
   deployed by the Delivery in force, and the new Delivery takes over after its deploy.

## Consequences
- Editing a working copy changes nothing that runs. Confirming, committing and approving do not
  either; deploying does.
- The self domains' events name their commit from now on. Their earlier events keep
  `domain_version` 1.
- Until a domain's first recorded deploy, it runs its approved `main`. For both self domains
  today, `main` is the commit that was last deployed and verified (#147, #140).
- `toprope-harness --composition` and the regeneration check keep reading the files. They check
  what is about to be committed, not what runs.
