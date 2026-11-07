# ADR-0044: Approval needs TLC's check

- Link: ③ works as built, ① iterate safely · Status: accepted · 2026-11-07 · decided by:
  SteamShon (the recommendation; drafted by the assistant)
- Builds on: ADR-0043 (the TLC cross-check), ADR-0039 (human requests), ADR-0032 (checks
  recorded on commits)

## Context
ADR-0043 runs TLC in a `tla` CI job on every pull request. The harness, in the change check,
finds a break one step away from its small world. A break that first needs a state the small
world never builds is TLC's alone (`docs/harness.md`, "What each one catches"). TLC found two such
breaks in the self domains (#139).

So a commit could pass its change check and be approved in the loop, while TLC would fail it
on the pull request that carries it. At that point the commit is already `main` of its domain,
and possibly deployed. The review of #135 named this gap: a break that takes several steps is
caught after approval, not before.

An agent's cloud session cannot run TLC (ADR-0043, Decision 2). Approval of a self-domain commit
from a cloud session already runs in GitHub Actions, in the human-request workflow (ADR-0039).

## Decision
1. **TLC is a check of the change check.** With a TLC jar configured, the change check runs TLC
   on the commit's model level, with the same verdicts and replay as the `tla` job, and records
   the `tla` check on the commit. Without a jar, `tla` is recorded as not run.
2. **A kernel with TLC approves only a commit TLC checked.** If the kernel has a jar
   (`TOPROPE_TLC_JAR`), `approve_commit` refuses a commit whose newest `tla` record is not a
   pass. A check run earlier, where no jar was configured, does not count.
3. **The human-request workflow has TLC.** Its approval job installs the `tla` job's pinned TLC
   and sets `TOPROPE_TLC_JAR`. A request with `approve_commit` must run `check_commit` on the
   same commit before it, in the same request. `human_request.py` refuses an approval without the
   jar.

## Consequences
- An approval from a cloud session waits a few more minutes for TLC.
- A local run without a jar approves as before; the `tla` job on the pull request remains the
  backstop for it.
- A break TLC finds that the harness also reports passes the `tla` check: the harness check
  already fails the commit on it.
- Item 4 of umbrella #143 (one change, one request) builds on the check-then-approve order
  required here.
