# Examples

Each example is one scenario from the declarations. Each starts from the named world fixture.

## Authoring

### approve-only-after-a-passing-check
Start: commit C2 (domain authoring, seq 2, content c3d4, branch work, interface 1.1.0, stage recorded, checks_passed false).
1. Role owner takes approve_commit on C2. Expected: denied by precondition `checks-pass`.
2. The kernel takes record_check on C2 with passed: true, summary: "passes". Expected: C2.checks_passed is true.
3. Role owner takes approve_commit on C2. Expected: C2.stage is recorded.
4. The kernel takes record_approval on C2 with approved: true, main: C2. Expected: C2.approved is true.
5. Role owner takes approve_commit on C2. Expected: denied by precondition `not-approved`.

### a-confirmed-element-is-not-unknown-again
Start: element E1 (path purpose, origin S-docs, review proposed).
1. Role owner takes confirm_element on E1. Expected: E1.review is confirmed.
2. Role expert takes mark_unknown on E1. Expected: denied by the transition table (matrix), with the reason shown.

### a-decision-is-taken-once
Start: DecisionRequest DR1 (element E1, subject "Which success metric?", stage open).
1. Role owner takes decide on DR1 with choice: A. Expected: DR1.stage is decided and DR1.choice is A.
2. Role owner takes decide on DR1 with choice: B. Expected: denied by the transition table (matrix).

### a-link-is-fetched-once
Start: Source S-docs (kind records, path docs, stage fetched, sha256 5f1c).
1. Role owner takes fetch_source on S-docs. Expected: denied by the transition table (matrix).

## Delivery

### deliver-preview-deploy-verify
Start: DeliveryRequest R1 (domain authoring, commit 2-c3d4, interface 1.1.0, environment local, approver ana, stage requested).
1. Role approver takes deploy on R1. Expected: denied by the transition table (matrix), with the reason shown.
2. Role approver takes preview on R1. Expected: R1.stage is previewing.
3. The kernel takes record_build on R1 with build: b1, harness_ok: true. Expected: R1.stage is previewed and R1.harness_ok is true.
4. Role approver takes deploy on R1. Expected: R1.stage is deploying.
5. The kernel takes record_deployment on R1 with deployed: true, error: "". Expected: R1.stage is done and R1.deployed is true.
6. Role approver takes verify on R1 with verified: true. Expected: R1.stage is verified and R1.verified is true.

### a-failed-harness-is-never-deployed
Start: DeliveryRequest R2 (commit 3-e5f6, stage previewed, build b2, harness_ok false).
1. Role approver takes deploy on R2. Expected: denied by precondition `harness-passed`.

### a-refused-deploy-is-not-verified-and-can-be-retried
Start: DeliveryRequest R3 (commit 4-a7b8, interface 1.2.0, stage done, build b3, harness_ok true, deployed false, refusal "stranded: E-live (state 'ended' is gone)").
1. Role approver takes verify on R3 with verified: true. Expected: denied by precondition `deployed`.
2. Role approver takes preview on R3. Expected: R3.stage is previewing.
