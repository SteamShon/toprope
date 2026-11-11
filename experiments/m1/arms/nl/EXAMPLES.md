# Worked examples

Each example is a scenario from the declarations. "denied_by: matrix" means the transition table denies the step; "reason_shown" means the deny reason is shown.

## Authoring

### approve-only-after-a-passing-check
Given: world object C2 (seq 2, checks_passed false, not approved).
1. owner takes `approve_commit` on C2. Expected: denied by precondition `checks-pass`.
2. external kernel takes `record_check` on C2 with passed = true, summary = "passes". Expected: C2.checks_passed is true.
3. owner takes `approve_commit` on C2. Expected: C2.stage is recorded.
4. external kernel takes `record_approval` on C2 with approved = true, main = C2. Expected: C2.approved is true.
5. owner takes `approve_commit` on C2. Expected: denied by precondition `not-approved`.

### a-confirmed-element-is-not-unknown-again
Given: world object E1 (review proposed).
1. owner takes `confirm_element` on E1. Expected: E1.review is confirmed.
2. expert takes `mark_unknown` on E1. Expected: denied by the matrix, with the reason shown.

### a-decision-is-taken-once
Given: world object DR1 (stage open).
1. owner takes `decide` on DR1 with choice = A. Expected: DR1.stage is decided; DR1.choice is A.
2. owner takes `decide` on DR1 with choice = B. Expected: denied by the matrix.

### a-link-is-fetched-once
Given: world object S-docs (stage fetched).
1. owner takes `fetch_source` on S-docs. Expected: denied by the matrix.

## Delivery

### deliver-preview-deploy-verify
Given: world object R1 (stage requested).
1. approver takes `deploy` on R1. Expected: denied by the matrix, with the reason shown.
2. approver takes `preview` on R1. Expected: R1.stage is previewing.
3. external kernel takes `record_build` on R1 with build = b1, harness_ok = true. Expected: R1.stage is previewed; R1.harness_ok is true.
4. approver takes `deploy` on R1. Expected: R1.stage is deploying.
5. external kernel takes `record_deployment` on R1 with deployed = true, error = "". Expected: R1.stage is done; R1.deployed is true.
6. approver takes `run_probes` on R1. Expected: R1.stage is done.
7. external kernel takes `record_probes` on R1 with passed = true, summary = "passed: 3 of 3 scenario(s) pass; 1 object(s) checked". Expected: R1.probes_passed is true.
8. approver takes `verify` on R1. Expected: R1.stage is verified; R1.verified is true.

### a-failed-harness-is-never-deployed
Given: world object R2 (stage previewed, harness_ok false).
1. approver takes `deploy` on R2. Expected: denied by precondition `harness-passed`.

### a-refused-deploy-is-not-verified-and-can-be-retried
Given: world object R3 (stage done, deployed false).
1. approver takes `verify` on R3. Expected: denied by precondition `deployed`.
2. approver takes `run_probes` on R3. Expected: denied by precondition `deployed`.
3. approver takes `preview` on R3. Expected: R3.stage is previewing.

### verify-needs-probes-that-passed
Given: world object R4 (stage done, deployed true).
1. approver takes `verify` on R4. Expected: denied by precondition `probes-passed`, with the reason shown.
2. approver takes `run_probes` on R4. Expected: R4.stage is done.
3. external kernel takes `record_probes` on R4 with passed = false, summary = "R9: breaks verified-requests-were-deployed". Expected: R4.probes_passed is false.
4. approver takes `verify` on R4. Expected: denied by precondition `probes-passed`.
5. external kernel takes `record_probes` on R4 with passed = true, summary = "passed: 3 of 3 scenario(s) pass; 1 object(s) checked". Expected: R4.probes_passed is true.
6. approver takes `verify` on R4. Expected: R4.stage is verified; R4.verified is true.
