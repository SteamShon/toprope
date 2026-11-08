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

### an-approved-commit-gets-a-release-name
Start: commit C2 (domain authoring, seq 2, branch work, stage recorded, checks_passed true, approved unset) and commit C1 (approved true).
1. Role owner takes name_release on C2 with name: "Spring". Expected: denied by precondition `approved`.
2. Role owner takes name_release on C1 with name: "Spring". Expected: C1.release_name is "Spring".

### a-deputy-approves-while-the-owner-is-away
Start: commit C2 (domain authoring, seq 2, branch work, stage recorded, checks_passed true).
1. Role owner takes name_deputy with person: eli, until: 2026-12-01. Expected: a Deputy is created with stage active.
2. Role deputy (eli) takes approve_commit on C2. Expected: allowed; the kernel records the approver as eli.
3. Role owner takes end_deputy on the Deputy. Expected: Deputy.stage is ended.
4. Role owner takes end_deputy on the Deputy again. Expected: denied by the transition table (matrix).

### a-wording-only-commit-is-approved-without-a-check
Start: commit C3 (domain authoring, seq 3, content e5f6, branch work, interface 1.1.0, stage recorded, checks_passed unset, wording_only true).
1. Role owner takes approve_commit on C3. Expected: allowed; the change check has not been run.
2. The kernel takes record_approval on C3 with approved: true, main: C3. Expected: C3.approved is true.

### a-confirmed-element-is-not-unknown-again
Start: element E1 (path purpose, origin S-docs, review proposed).
1. Role owner takes confirm_element on E1 with reason: "Matches how we describe the purpose". Expected: E1.review is confirmed and E1.confirmation_reason is "Matches how we describe the purpose".
2. Role expert takes mark_unknown on E1. Expected: denied by the transition table (matrix), with the reason shown.

### a-wrong-proposal-is-withdrawn
Start: element E5 (path purpose, origin S-docs, review proposed) and element E1 (review confirmed).
1. Role owner takes withdraw_element on E5. Expected: E5.review is withdrawn.
2. Role owner takes withdraw_element on E1. Expected: denied by the transition table (matrix), with the reason shown.

### an-agent-confirms-only-wording-fixes
Start: element E2 (path purpose, origin S-docs, review proposed, wording_only true) and element E3 (path success-metric, origin S-docs, review proposed).
1. Role agent takes confirm_wording_element on E3. Expected: denied by precondition `wording-only`.
2. Role agent takes confirm_wording_element on E2. Expected: E2.review is confirmed.

### a-permission-element-needs-a-second-person
Start: element E4 (path approvers, origin S-docs, review proposed, permission true).
1. Role owner (ana) takes confirm_element on E4 with reason: "Matches who approves today". Expected: E4.review is confirmed and E4.first_confirmer is ana.
2. Role owner (ana) takes second_confirm_element on E4 with reason: "Agree". Expected: denied by precondition `different-person`.
3. Role expert (eli) takes second_confirm_element on E4 with reason: "Agree, checked the roles". Expected: E4.second_confirmer is eli.

### a-decision-is-taken-once
Start: DecisionRequest DR1 (element E1, subject "Which success metric?", stage open).
1. Role owner takes decide on DR1 with choice: A. Expected: DR1.stage is decided and DR1.choice is A.
2. Role owner takes decide on DR1 with choice: B. Expected: denied by the transition table (matrix).

### an-agent-settles-a-decision-the-owner-gave-in-chat
Start: DecisionRequest DR2 (element E1, subject "Which success metric?", stage open).
1. Role agent takes decide_from_chat on DR2 with choice: A, owner_words: "". Expected: denied by precondition `owner-words-written`.
2. Role agent takes decide_from_chat on DR2 with choice: A, owner_words: "Go with A for the success metric". Expected: DR2.stage is decided and DR2.choice is A.
3. Role agent takes decide_from_chat on DR2 with choice: B, owner_words: "Actually B". Expected: denied by the transition table (matrix).

### a-link-is-fetched-once
Start: Source S-docs (kind records, path docs, stage fetched, sha256 5f1c).
1. Role owner takes fetch_source on S-docs. Expected: denied by the transition table (matrix).

### a-required-stage-is-skipped-only-with-a-reason
Start: Draft D1 (domain authoring, branch work, stage open, current_stage a required stage).
1. Role owner takes skip_stage on D1 with stage: the current required stage, reason: "". Expected: denied by precondition `reason-written`.
2. Role owner takes skip_stage on D1 with the same stage, reason: "This domain has nothing to say at this stage". Expected: allowed; D1.stage is open.

## Delivery

### a-delivery-request-must-say-its-branch
Start: no delivery requests.
1. The system takes request_delivery with domain_id: authoring, commit: 2-c3d4, interface: 1.1.0, environment: local, approver: ana, branch: "". Expected: denied by precondition `branch-stated`.
2. The system takes request_delivery with the same params and branch: main. Expected: a DeliveryRequest is created with branch main, stage requested.

### a-delivery-request-shows-the-commit-it-replaced
Start: Environment local (current_commit 1-a1b2); no delivery requests.
1. The system takes request_delivery with domain_id: authoring, commit: 2-c3d4, interface: 1.1.0, environment: local, approver: ana, branch: main. Expected: a DeliveryRequest is created with replaced_commit 1-a1b2.

### deliver-preview-deploy-verify
Start: DeliveryRequest R1 (domain authoring, commit 2-c3d4, interface 1.1.0, environment local, approver ana, branch main, stage requested).
1. Role approver takes deploy on R1. Expected: denied by the transition table (matrix), with the reason shown.
2. Role approver takes preview on R1. Expected: R1.stage is built (a preview finishes at once).
3. The kernel takes record_build on R1 with build: b1, harness_ok: true. Expected: R1.stage is built and R1.harness_ok is true.
4. Role approver takes deploy on R1. Expected: R1.stage is deploying.
5. The kernel takes record_deployment on R1 with deployed: true, error: "". Expected: R1.stage is done and R1.deployed is true.
6. Role approver takes verify on R1 with verified: true. Expected: R1.stage is verified and R1.verified is true.

### a-passing-preview-deploys-on-its-own
Start: DeliveryRequest R5 (commit 2-c3d4, approver ana, stage requested).
1. The system takes auto_deploy on R5. Expected: denied by the transition table (matrix), with the reason shown.
2. Role approver takes preview on R5, and the kernel takes record_build on R5 with build: b5, harness_ok: true. Expected: R5.stage is built.
3. The system takes auto_deploy on R5. Expected: R5.stage is deploying, with no one pressing deploy.

### a-failed-harness-is-never-deployed
Start: DeliveryRequest R2 (commit 3-e5f6, stage built, build b2, harness_ok false).
1. Role approver takes deploy on R2. Expected: denied by precondition `harness-passed`.

### a-dry-run-verifies-before-deploy
Start: DeliveryRequest R4 (commit 2-c3d4, stage built, build b4, harness_ok true, deployed unset).
1. Role approver takes verify on R4 with verified: true. Expected: allowed; R4.dry_run is true, R4.verified is unset and R4.stage is built.
2. Role approver takes deploy on R4. Expected: R4.stage is deploying.

### a-refused-deploy-is-not-verified-and-can-be-retried
Start: DeliveryRequest R3 (commit 4-a7b8, interface 1.2.0, stage done, build b3, harness_ok true, deployed false, refusal "stranded: E-live (state 'ended' is gone)").
1. Role approver takes verify on R3 with verified: true. Expected: denied by precondition `deployed`.
2. Role approver takes preview on R3. Expected: R3.stage is built.
