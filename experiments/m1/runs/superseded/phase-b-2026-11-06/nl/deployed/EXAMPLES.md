# EXAMPLES

Worked examples, one per scenario. "denied_by: matrix" means the transition table denies the step; a precondition id means that named precondition denies it.

## Authoring

### approve-only-after-a-passing-check
Given: world object C2 (seq 2, checks_passed false, not approved).
1. owner takes `approve_commit` on C2. Expected: denied by precondition `checks-pass`.
2. external kernel takes `record_check` on C2 with passed = true, summary = "passes". Expected: C2.checks_passed is true.
3. owner takes `approve_commit` on C2. Expected: C2.stage is recorded.
4. external kernel takes `record_approval` on C2 with approved = true, main = C2. Expected: C2.approved is true.
5. owner takes `approve_commit` on C2. Expected: denied by precondition `not-approved`.

### the-owner-names-an-approved-commit-as-a-release
Given: world object C1 (approved true) and C3 (not approved).
1. owner takes `name_release` on C1 with release_name = "Spring". Expected: C1.release_name is Spring.
2. owner takes `name_release` on C3 with release_name = "Summer". Expected: denied by precondition `approved`.

### a-confirmed-element-is-not-unknown-again
Given: world object E1 (review proposed).
1. owner takes `confirm_element` on E1 with reason = "Matches what the scope document says." Expected: E1.review is confirmed and E1.confirm_reason is "Matches what the scope document says.".
2. expert takes `mark_unknown` on E1. Expected: denied by the matrix, and the reason is shown ("A confirmed element changes by a new proposal and a new commit, not by marking it unknown.").

### the-owner-withdraws-a-wrong-proposal
Given: world object E1 (review proposed) and E2 (review confirmed).
1. owner takes `withdraw_element` on E1. Expected: E1.review is withdrawn.
2. owner takes `withdraw_element` on E2. Expected: denied by the matrix, and the reason is shown ("A confirmed element changes by a new proposal and a new commit, not by withdrawing it.").

### an-agent-confirms-only-wording-fixes
Given: world object E1 (review proposed, wording_only not set).
1. agent takes `confirm_wording_fix` on E1. Expected: denied by precondition `wording-only`.

### a-decision-is-taken-once
Given: world object DR1 (stage open).
1. owner takes `decide` on DR1 with choice = A. Expected: DR1.stage is decided and DR1.choice is A.
2. owner takes `decide` on DR1 with choice = B. Expected: denied by the matrix.

### an-agent-settles-a-decision-on-the-owners-chat-word
Given: world object DR1 (stage open).
1. agent takes `decide` on DR1 with choice = A and no owner_words. Expected: denied by precondition `owner-said-so`.
2. agent takes `decide` on DR1 with choice = A and owner_words = "Go with A." Expected: DR1.stage is decided and DR1.choice is A.
3. agent takes `decide` on DR1 with choice = B and owner_words = "Go with B." Expected: denied by the matrix.

### a-link-is-fetched-once
Given: world object S-docs (stage fetched).
1. owner takes `fetch_source` on S-docs. Expected: denied by the matrix.

## Delivery

### deliver-preview-deploy-verify
Given: world object R1 (stage requested).
1. approver takes `deploy` on R1. Expected: denied by the matrix, and the reason is shown ("Preview it first.").
2. approver takes `preview` on R1. Expected: R1.stage is built at once.
3. external kernel takes `record_build` on R1 with build = b1, harness_ok = true. Expected: R1.stage is built and R1.harness_ok is true.
4. approver takes `deploy` on R1. Expected: R1.stage is deploying.
5. external kernel takes `record_deployment` on R1 with deployed = true, error = "" (empty). Expected: R1.stage is done and R1.deployed is true.
6. approver takes `verify` on R1 with verified = true. Expected: R1.stage is verified and R1.verified is true.

### a-delivery-request-must-say-its-branch
Given: no delivery request yet.
1. system takes `request_delivery` with domain_id = authoring, commit = 3-e5f6, interface = 1.2.0, environment = local, approver = ana, branch = "" (empty). Expected: denied by precondition `branch-stated`.
2. system takes `request_delivery` with the same params and branch = work. Expected: a DeliveryRequest is created with stage requested and branch work.

### verify-before-deploy-records-a-dry-run
Given: world object R1 (stage requested).
1. approver takes `verify` on R1 with verified = true. Expected: R1.stage is requested, R1.dry_run is true and R1.verified is not set.
2. approver takes `deploy` on R1. Expected: denied by the matrix, and the reason is shown ("Preview it first.").

### a-failed-harness-is-never-deployed
Given: world object R2 (stage built, harness_ok false).
1. approver takes `deploy` on R2. Expected: denied by precondition `harness-passed`.

### a-refused-deploy-is-not-verified-and-can-be-retried
Given: world object R3 (stage done, deployed false).
1. approver takes `verify` on R3 with verified = true. Expected: denied by precondition `deployed`.
2. approver takes `preview` on R3. Expected: R3.stage is built.
