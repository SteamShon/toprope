# Worked examples

One example per declared scenario. Names refer to the sample worlds in SKILL.md.

## Authoring

### 1. approve-only-after-a-passing-check
Start: commit C2 (checks failed, not approved).
1. Owner ana tries `approve_commit` on C2. **Denied** by `checks-pass`: the change check has not passed.
2. The kernel takes `record_check` on C2 with passed = true, summary "passes". C2.checks_passed becomes true.
3. Owner ana (a person) takes `approve_commit` on C2. It is allowed; C2 stays in stage `recorded`.
4. The kernel takes `record_approval` on C2 with approved = true, main = C2. C2.approved is true.
5. Owner tries `approve_commit` on C2 again. **Denied** by `not-approved`: already approved; approve a newer commit.

### 2. a-confirmed-element-is-not-unknown-again
Start: element E1 (proposed).
1. Owner (a person) takes `confirm_element` on E1. E1.review becomes `confirmed`.
2. Expert eli tries `mark_unknown` on E1. **Denied** by the transition table, with the reason shown: a confirmed element changes by a new proposal and a new commit, not by marking it unknown.

### 3. a-decision-is-taken-once
Start: DecisionRequest DR1 (open).
1. Owner takes `decide` on DR1 with choice A. DR1.stage becomes `decided` and DR1.choice is A.
2. Owner tries `decide` on DR1 with choice B. **Denied** by the transition table: already decided; a new decision needs a new request.

### 4. a-link-is-fetched-once
Start: source S-docs (already fetched, sha256 5f1c).
1. Owner tries `fetch_source` on S-docs. **Denied** by the transition table: a link is fetched once into a snapshot; add a new source to read it again.

## Delivery

### 5. deliver-preview-deploy-verify
Start: request R1 (requested).
1. Approver ana tries `deploy` on R1. **Denied** by the transition table, reason shown: preview it first.
2. Approver takes `preview` on R1. Stage becomes `previewing`.
3. The kernel takes `record_build` with build b1, harness_ok true. Stage becomes `previewed`, harness_ok true.
4. Approver (a person) takes `deploy`. Stage becomes `deploying`.
5. The kernel takes `record_deployment` with deployed true and no error. Stage becomes `done`, deployed true.
6. Approver (a person) takes `verify` with verified true. Stage becomes `verified`, verified true.

### 6. a-failed-harness-is-never-deployed
Start: request R2 (previewed, harness_ok false).
1. Approver tries `deploy` on R2. **Denied** by `harness-passed`: deploy only a build whose harness passed.

### 7. a-refused-deploy-is-not-verified-and-can-be-retried
Start: request R3 (done, deployed false, refusal "stranded: E-live (state 'ended' is gone)").
1. Approver tries `verify` on R3 with verified true. **Denied** by `deployed`: only a deployment that happened can be verified.
2. Approver takes `preview` on R3. Allowed from `done`; stage becomes `previewing`, starting a retry.
