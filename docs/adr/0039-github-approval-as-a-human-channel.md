# ADR-0039: A GitHub environment approval is a human channel

- Link: ③ works as built, ⑥ org productivity · Status: accepted · 2026-11-06 · decided by:
  SteamShon (option "A"; drafted by the assistant)
- Amends: ADR-0037 resolved 2 (a person is identified by their git identity), AGENTS.md
  ("Freezing and amending")

## Context
Some steps must be taken by the researcher themself: freezing an instrument, confirming
elements, approving a commit, deploying (`requires: human`; probe P01: the agent does not
decide on its own, even when told the owner agrees in chat). Until now they ran on the
researcher's own terminal, identified by their git email (ADR-0037).

From a cloud session that is impossible, and nothing there tells the researcher apart from
the agent: the agent commits with any author, and its GitHub posts appear under the
researcher's account. A PR comment such as `/toprope freeze` would prove nothing.

GitHub can tell them apart in one place: a job that targets a protected **environment** with
a required reviewer waits until a reviewer presses "Approve and deploy", on the web or the
GitHub mobile app, and GitHub records who approved. The agent has no tool for that button.

## Decision
1. **A human request is a file.** The agent (or anyone) commits `.toprope/requests/<id>.yaml`
   on a work branch: a summary and a list of steps from a fixed set (freeze, freeze the
   binding, amend with a reason, and a `toprope-run` action of a self domain).
2. **The researcher approves it in GitHub.** `.github/workflows/human-request.yml` validates
   the request and shows it on the run page, then its `act` job waits on the environment
   `researcher`, whose required reviewer is the researcher. Nothing runs until they approve.
3. **The approver is the identity.** The job reads who approved the run from GitHub and looks
   that login up in `toprope.identity.yaml` (`github:` on a person). Actions run as that person
   (`toprope-run --identity github`); an unlisted approver stops the job. A person-only action
   needs no terminal prompt here: the approval is the person's confirmation.
4. **It runs exactly what was shown.** The `act` job checks out the commit the request was
   validated at, and pushes its result to the branch only as a fast-forward of that commit.
   The commit removes the request file and records the approver and the run in its trailers.
   It then runs the PR's `status` check on the new head.
5. **Unchanged:** a person on their own machine still uses their git identity (ADR-0037); this
   adds a channel for the cloud. Requests never run on `main` or `develop`.

## Consequences
- The researcher's part shrinks to pressing one button, from anywhere, and the record of who
  decided is GitHub's, which is stronger than a self-asserted git email.
- The guarantee is that the agent has no tool to approve a deployment review. It is not
  cryptographic: a credential with that permission could approve. Signed commits remain the
  stronger, local option.
- The maintainer sets up the environment once (Repository settings → Environments →
  `researcher` → Required reviewers: the researcher; leave "Prevent self-review" off, since
  the researcher's own account pushes the request), and lets workflows write contents.
