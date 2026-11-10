# Worked examples

Each example is a scenario from the declarations. "denied_by: matrix" means the transition table denies the step; "reason_shown" means the deny reason is shown.

## Authoring

### approve-only-after-a-passing-check
Given: world object C2 (seq 2, checks_passed false, not approved).
1. owner takes `approve_commit` on C2. Expected: denied by precondition `checks-pass`.
2. external kernel takes `record_check` on C2 with passed = true, summary = "passes", checked_at = now. Expected: C2.checks_passed is true.
3. owner takes `approve_commit` on C2 (the check is less than a day old). Expected: C2.stage is recorded.
4. external kernel takes `record_approval` on C2 with approved = true, main = C2. Expected: C2.approved is true.
5. owner takes `approve_commit` on C2. Expected: denied by precondition `not-approved`.

### a-stale-check-does-not-count
Given: world object C3 (checks_passed true, checked_at more than a day ago, not approved).
1. owner takes `approve_commit` on C3. Expected: denied by precondition `checks-pass`.
2. owner takes `check_commit` on C3; external kernel takes `record_check` on C3 with passed = true, checked_at = now. Expected: C3.checks_passed is true.
3. owner takes `approve_commit` on C3. Expected: C3.stage is recorded.

### a-wording-only-commit-is-approved-without-a-check
Given: world object C3 modified so checks_passed is not set (not approved).
1. owner takes `approve_commit` on C3 without wording_only. Expected: denied by precondition `checks-pass`.
2. owner takes `approve_commit` on C3 with wording_only = true. Expected: C3.stage is recorded; C3.wording_only is true.
3. external kernel takes `record_approval` on C3 with approved = true, main = C3. Expected: C3.approved is true.

### a-deputy-approves-while-the-owner-is-away
Given: world object C3 (checks_passed true, not approved).
1. owner takes `name_deputy` with person = eli. Expected: a Deputy is created for eli, stage named.
2. owner takes `set_away` on that Deputy with away = true. Expected: the Deputy's away is true.
3. deputy takes `approve_commit` on C3. Expected: C3.stage is recorded; the approver recorded is the deputy.
4. external kernel takes `record_approval` on C3 with approved = true, main = C3. Expected: C3.approved is true.

### the-owner-names-an-approved-commit-as-a-release
Given: world object C1 (approved) and C3 (not approved).
1. owner takes `name_release` on C3 with release_name = "spring". Expected: denied by precondition `approved`.
2. owner takes `name_release` on C1 with release_name = "spring". Expected: C1.stage is recorded; C1.release_name is "spring".

### a-confirmed-element-is-not-unknown-again
Given: world object E1 (review proposed).
1. owner takes `confirm_element` on E1 with reason = "Matches what the owner described in the interview". Expected: E1.review is confirmed; E1.confirm_reason is "Matches what the owner described in the interview".
2. expert takes `mark_unknown` on E1. Expected: denied by the matrix, with the reason shown.

### an-agent-confirms-only-wording-fixes
Given: world object E1 (review proposed, wording_only not set).
1. agent takes `confirm_wording_element` on E1. Expected: denied by precondition `wording-only`.
2. owner takes `propose_element` for a wording fix with wording_only = true. Expected: the new element has wording_only true and review proposed.
3. agent takes `confirm_wording_element` on that element with reason = "Only fixes wording". Expected: its review is confirmed; its confirm_reason is "Only fixes wording".

### a-decision-is-taken-once
Given: world object DR1 (stage open).
1. owner takes `decide` on DR1 with choice = A. Expected: DR1.stage is decided; DR1.choice is A.
2. owner takes `decide` on DR1 with choice = B. Expected: denied by the matrix.

### an-agent-settles-a-decision-the-owner-gave-in-chat
Given: world object DR1 (stage open).
1. agent takes `decide_from_chat` on DR1 with choice = A and no owner_words. Expected: denied by precondition `owner-said-so`.
2. agent takes `decide_from_chat` on DR1 with choice = A and owner_words = "Go with A". Expected: DR1.stage is decided; DR1.choice is A; DR1.owner_words is "Go with A".
3. owner takes `decide` on DR1 with choice = B. Expected: denied by the matrix.

### the-owner-may-skip-a-required-stage-with-a-reason
Given: world object D1 (stage open), whose current stage is required.
1. owner takes `skip_stage` on D1 with stage = the current stage and reason = "This domain has nothing to say at this stage". Expected: D1.stage is open; the kernel is asked to skip the stage with that reason.
2. external kernel takes `record_skip` on D1 with skipped = true. Expected: D1.stage is open.

### a-link-is-fetched-once
Given: world object S-docs (stage fetched).
1. owner takes `fetch_source` on S-docs. Expected: denied by the matrix.

## Delivery

### deliver-preview-deploy-verify
Given: world object R1 (stage requested).
1. approver takes `deploy` on R1. Expected: denied by the matrix, with the reason shown.
2. approver takes `preview` on R1. Expected: R1.stage is built.
3. external kernel takes `record_build` on R1 with build = b1, harness_ok = true. Expected: R1.stage is built; R1.harness_ok is true.
4. approver takes `deploy` on R1. Expected: R1.stage is deploying.
5. external kernel takes `record_deployment` on R1 with deployed = true, error = "". Expected: R1.stage is done; R1.deployed is true.
6. approver takes `run_probes` on R1. Expected: R1.stage is done.
7. external kernel takes `record_probes` on R1 with passed = true, summary = "passed: 3 of 3 scenario(s) pass; 1 object(s) checked". Expected: R1.probes_passed is true.
8. approver takes `verify` on R1. Expected: R1.stage is verified; R1.verified is true.

### a-passing-preview-deploys-on-its-own
Given: world object R1 (stage requested).
1. approver takes `preview` on R1. Expected: R1.stage is built.
2. external kernel takes `record_build` on R1 with build = b1, harness_ok = true. Expected: R1.harness_ok is true.
3. system takes `deploy` on R1, with no person pressing deploy. Expected: R1.stage is deploying.
4. external kernel takes `record_deployment` on R1 with deployed = true, error = "". Expected: R1.stage is done; R1.deployed is true.

### a-delivery-request-must-state-its-branch
1. system takes `request_delivery` with domain_id = authoring, commit = 3-e5f6, interface = 1.2.0, environment = local, approver = ana, and no branch. Expected: denied by precondition `branch-stated`.
2. system takes `request_delivery` with the same parameters and branch = main. Expected: a DeliveryRequest is created with branch main and stage requested.

### a-failed-harness-is-never-deployed
Given: world object R2 (stage built, harness_ok false).
1. approver takes `deploy` on R2. Expected: denied by precondition `harness-passed`.

### a-refused-deploy-is-not-verified-and-can-be-retried
Given: world object R3 (stage done, deployed false).
1. approver takes `verify` on R3. Expected: denied by precondition `deployed`.
2. approver takes `run_probes` on R3. Expected: denied by precondition `deployed`.
3. approver takes `preview` on R3. Expected: R3.stage is built.

### verify-needs-probes-that-passed
Given: world object R4 (stage done, deployed true).
1. approver takes `verify` on R4. Expected: denied by precondition `probes-passed`, with the reason shown.
2. approver takes `run_probes` on R4. Expected: R4.stage is done.
3. external kernel takes `record_probes` on R4 with passed = false, summary = "R9: breaks verified-requests-were-deployed". Expected: R4.probes_passed is false.
4. approver takes `verify` on R4. Expected: denied by precondition `probes-passed`.
5. external kernel takes `record_probes` on R4 with passed = true, summary = "passed: 3 of 3 scenario(s) pass; 1 object(s) checked". Expected: R4.probes_passed is true.
6. approver takes `verify` on R4. Expected: R4.stage is verified; R4.verified is true.

### a-dry-run-verifies-before-deploy-without-verifying
Given: world object R2 (stage built, not deployed).
1. approver takes `verify` on R2 without dry_run. Expected: denied by precondition `deployed`.
2. approver takes `verify` on R2 with dry_run = true. Expected: R2.stage is built; R2.dry_run is true; R2.verified is not set.
