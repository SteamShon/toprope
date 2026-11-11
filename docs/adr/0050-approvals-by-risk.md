# ADR-0050: How much one approval covers depends on the change's risk

- Link: ① iterate safely, ⑥ org productivity · Status: accepted · 2026-11-09 · decided by:
  SteamShon ("추천대로": the recommendation on each open point; drafted by the assistant; ADR-0049, C2)
- Builds on: ADR-0039 (human requests), ADR-0041 (the one way across), ADR-0045 (the self domains
  run their deployed commit), ADR-0048 (the capability diff), ADR-0049 (usability before M2)

## Context
After theme 1 of ADR-0049, a change to a self domain takes one agent command (`toprope-change`)
and one human request. That request confirms, commits, checks and approves. Shipping the
approved commit is more steps that only a person may take: `deliver`, `deploy` and `verify`
(`requires: human`), with `preview` and `run_probes` between them. Today each is its own command
or its own request, so a person approves two or three times for every change, whatever the
change is. F1's baseline is 8.3 commands by a person per approved change; ADR-0049's target is
one approval for a low-risk change.

A human request can already hold every one of those steps (`target: delivery:$commit:local`),
and `run` stops at the first step that fails. What is missing is a rule for when one approval
may cover all of them, and the person's sight of why.

Two things must not change: only a person confirms, approves, deploys and verifies (ADR-0041,
`requires: human`), and an agent never takes those steps. This ADR changes how many of a
person's steps one approval covers. It changes nothing about who takes them.

## Decision
1. **Risk is computed, not declared.** `check_commit` classifies the commit it checks:
   - **low** when every check passed, the capability diff (ADR-0048) has no warning (no new
     path to an outcome, no dropped `requires: human`, precondition or rule), no element was
     removed, no invariant or outcome rule changed, and the in-flight check found no object in
     a state the change removes;
   - **high** otherwise, with the reasons (each check, warning or removed element that made it
     high).
   The classification is recorded with the checks (`risk` and `risk_reasons`), so it is part
   of the commit's record.
2. **A low-risk change ships on one approval.** For a low-risk commit, `toprope-change` writes
   one request with every step: confirm, commit, check, approve, deliver, preview, deploy,
   run the probes, verify. `run` stops at the first failing step, so a failed preview or probe
   leaves the commit approved and undeployed, or deployed and unverified, as today when those
   steps fail by hand.
3. **A high-risk change takes two approvals.** The first request stops at `approve_commit`. The
   second, written after the preview, holds deliver, deploy, run the probes, verify. The person
   reads the preview's harness result and the risk reasons before the second approval.
4. **The person sees the risk before approving.** The request's run page shows the risk, its
   reasons and the B5 diff. `check_commit` runs again inside the request, so a commit that
   became high-risk after the request was written (a rebase, a changed base) is refused by
   the request: its `approve_commit` step requires the recorded risk to be `low` when the
   request has deploy steps.
5. **The floor is unchanged.** Every step runs as the approving person (ADR-0039); an agent never
   approves, deploys or verifies; a request's steps come from the fixed set. Verifying on the
   same approval means the person verifies in advance, on the condition that the probes pass;
   the run page says so in those words.

## Consequences
- `check_commit` records `risk`; `human_request.py check` refuses deploy steps after an
  `approve_commit` unless the commit's recorded risk is `low` (checked when the request runs).
- `toprope-change` writes the one-approval request for low risk and the two-approval pair for
  high risk.
- F1 measures the result: approvals per approved change, by risk.

## Resolved (researcher, 2026-11-09: the recommendation in each case)
1. **Verify in advance.** For a low-risk change, the one approval covers `verify`, on the
   condition that the probes pass: the probes are the evidence a person would read, and a
   failed probe stops the run before `verify`. A high-risk change verifies on its second
   approval, as written above.
2. **Who may take a person-only step.** A change to `requires: human`, to an `approval` rule
   (ADR-0046), to an outcome rule whose `requires` names a person or a role (ADR-0048), or to
   the roles on a person-only action is always **high**, even when it narrows.
3. **Narrowings.** Otherwise, a narrowing (the capability diff's info) leaves a change low.

## Rejected
- **Risk declared by the author.** An agent would declare its own change low risk.
- **Skipping the person for low-risk changes.** That is a change to ADR-0041's floor, which
  M2 has not tested.
