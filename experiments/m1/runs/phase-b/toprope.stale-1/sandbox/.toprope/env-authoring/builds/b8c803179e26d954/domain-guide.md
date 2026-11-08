# Domain guide: `authoring` (version 10)

_Generated from the declaration at build time. Do not edit: change the declaration._

## Purpose

A domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code.

**Success metric:** human minutes from an owner's intent to a confirmed, compiled domain version (down is better)

> Domain owners now turn the workflow in their heads into a declared, checked domain without writing code. Every change shows what it breaks before anything is deployed.

## People and things

**Roles:** `owner` (ana), `expert` (eli). Agents act only on a person's behalf, with a grant.

- **Answer**: The owner's answer, in their words; its decisions become proposed elements. Stages: `recorded` (starts `recorded`).
  - facts: `words` (string), `decisions` (string), `ref` (string, optional)
- **Commit**: An immutable snapshot of the working copy on a branch. Stages: `recorded` (starts `recorded`).
  - facts: `seq` (integer), `content` (string), `branch` (string), `author` (string, optional), `message` (string, optional), `interface` (string), `domain_id` (string), `checks_passed` (boolean, optional), `failing` (string, optional), `approved` (boolean, optional), `main` (string, optional), `last_evidence` (string, optional), `evidence_error` (string, optional)
- **DecisionRequest**: A decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox. Stages: `open`, `decided` (starts `open`).
  - facts: `subject` (string), `grounds` (string), `recommendation` (string), `choice` (string, optional)
- **Draft**: The working copy of a domain's declaration on a branch: what a commit snapshots. Stages: `open` (starts `open`).
  - facts: `domain_id` (string), `declaration` (string), `branch` (string), `current_stage` (string, optional), `bundle` (string, optional), `merging` (string, optional), `conflicts` (integer, optional)
- **Element**: One part of the draft declaration (an object, action, cell, invariant...), proposed by an agent or confirmed by a person. Stages: `proposed`, `unknown`, `confirmed` (starts `proposed`).
  - facts: `path` (string), `value` (string, optional), `cites` (string), `issues` (integer, optional), `issue_summary` (string, optional)
- **Question**: A question in a stage's bundle, for the owner to answer.
  - facts: `stage` (string), `text` (string)
- **Source**: Where raw material lives: code, records, transcripts or the interview log. Stages: `added`, `fetched` (starts `added`).
  - facts: `kind` (one of repository, records, transcripts, interview-log), `path` (string), `local_only` (boolean), `sha256` (string, optional)

**Links** (read like a field of the `from` object):

| link | from → to | cardinality | required |
| --- | --- | --- | --- |
| `DecisionRequest.element` | DecisionRequest → Element | many-to-one | no |
| `Element.origin` | Element → Source | many-to-one | no |
| `Commit.parents` | Commit → Commit | many-to-many | no |
| `Answer.question` | Answer → Question | many-to-one | yes |

## Actions

🔒 only a person may take it · 📝 recorded as a decision

| action | who | on | needs first | changes | starts | event |
| --- | --- | --- | --- | --- | --- | --- |
| `add_source` | owner | creates **Source**; params `kind` (one of repository, records, transcripts, interview-log), `path` (string), `local_only` (boolean, optional) | — | — | — | `SourceCreated` |
| `fetch_source` | owner | **Source** | — | the stage (per the matrix) | kernel `fetch_source` → `record_fetch` | `SourceFetchSource` |
| `record_fetch` | the kernel | **Source**; params `sha256` (string) | — | the stage (per the matrix); `target.sha256` ← `params.sha256` | — | `SourceRecordFetch` |
| `ask_question` | owner, expert | creates **Question**; params `stage` (string), `text` (string) | — | — | — | `QuestionCreated` |
| `answer_question` | owner, expert | creates **Answer**; params `question` (a Question), `words` (string), `decisions` (string) | — | — | kernel `record_answer` → `record_answer_ref` | `AnswerCreated` |
| `propose_element` | owner | creates **Element**; params `path` (string), `origin` (a Source), `cites` (string), `value` (string) | — | — | kernel `propose_element` → `record_proposal` | `ElementCreated` |
| `confirm_element` 🔒 | owner | **Element** | — | the stage (per the matrix) | kernel `confirm_element` → `record_confirmation` | `ElementConfirmElement` |
| `mark_unknown` | owner, expert | **Element** | — | the stage (per the matrix) | — | `ElementMarkUnknown` |
| `request_decision` | owner | creates **DecisionRequest**; params `element` (a Element), `subject` (string), `grounds` (string), `recommendation` (string) | — | — | — | `DecisionRequestCreated` |
| `decide` 🔒 📝 | owner | **DecisionRequest**; params `choice` (string), `rationale` (string, optional) | — | the stage (per the matrix); `target.choice` ← `params.choice` | — | `DecisionRequestDecide` |
| `commit_draft` | owner | **Draft** | — | the stage (per the matrix) | kernel `commit` → `record_commit` | `DraftCommitDraft` |
| `record_commit` | the kernel | creates **Commit**; params `seq` (integer), `content` (string), `interface` (string), `domain` (string), `branch` (string), `author` (string) | — | `target.domain_id` ← `params.domain` | — | `CommitCreated` |
| `check_commit` | owner | **Commit** | `not-approved`: An approved commit passed its check; check a new commit instead. | the stage (per the matrix) | kernel `change_check` → `record_check` | `CommitCheckCommit` |
| `record_check` | the kernel | **Commit**; params `passed` (boolean), `summary` (string) | `settled`: An approved commit's check is settled; a late result is not recorded. | the stage (per the matrix); `target.checks_passed` ← `params.passed`, `target.failing` ← `params.summary` | — | `CommitRecordCheck` |
| `approve_commit` 🔒 📝 | owner | **Commit**; params `rationale` (string, optional) | `checks-pass`: Run the change check, and approve only a commit that passes it.; `not-approved`: Already approved; approve a newer commit. | the stage (per the matrix) | kernel `approve_commit` → `record_approval` | `CommitApproveCommit` |
| `record_approval` | the kernel | **Commit**; params `approved` (boolean), `main` (string) | `approved-only-if-checked`: A commit is recorded as approved only if its change check passed. | the stage (per the matrix); `target.approved` ← `params.approved`, `target.main` ← `params.main` | — | `CommitRecordApproval` |
| `deliver` | owner | **Commit**; params `environment` (one of local) | `approved`: Only an approved commit is delivered. | the stage (per the matrix) | handoff `deliver_approved_commit` → delivery.request_delivery | `CommitDeliver` |
| `record_proposal` | the kernel | **Element**; params `issues` (integer), `summary` (string) | — | the stage (per the matrix); `target.issues` ← `params.issues`, `target.issue_summary` ← `params.summary` | — | `ElementRecordProposal` |
| `record_confirmation` | the kernel | **Element**; params `confirmed` (string, many) | — | the stage (per the matrix) | — | `ElementRecordConfirmation` |
| `record_answer_ref` | the kernel | **Answer**; params `ref` (string) | — | the stage (per the matrix); `target.ref` ← `params.ref` | — | `AnswerRecordAnswerRef` |
| `next_questions` | owner | **Draft** | — | the stage (per the matrix) | kernel `stage_questions` → `record_questions` | `DraftNextQuestions` |
| `record_questions` | the kernel | **Draft**; params `stage` (string), `bundle` (string), `questions` (string, many) | — | the stage (per the matrix); `target.current_stage` ← `params.stage`, `target.bundle` ← `params.bundle` | — | `DraftRecordQuestions` |
| `search` | owner | **Draft**; params `query` (string) | — | the stage (per the matrix) | kernel `search_sources` → `record_search` | `DraftSearch` |
| `record_search` | the kernel | **Draft**; params `refs` (string, many) | — | the stage (per the matrix) | — | `DraftRecordSearch` |
| `skip_stage` 🔒 | owner | **Draft**; params `stage` (string), `reason` (string) | — | the stage (per the matrix) | kernel `skip_stage` → `record_skip` | `DraftSkipStage` |
| `record_skip` | the kernel | **Draft**; params `skipped` (boolean) | — | the stage (per the matrix) | — | `DraftRecordSkip` |
| `open_draft` | owner | creates **Draft**; params `domain_id` (string), `declaration` (string), `branch` (string) | — | — | — | `DraftCreated` |
| `merge_main` | owner | **Draft** | — | the stage (per the matrix) | kernel `merge_main` → `record_merge` | `DraftMergeMain` |
| `checkout_commit` | owner | **Draft**; params `commit` (string) | — | the stage (per the matrix) | kernel `checkout` → `record_checkout` | `DraftCheckoutCommit` |
| `confirm_all_proposed` 🔒 | owner | **Draft** | — | the stage (per the matrix) | kernel `confirm_element` → `record_confirm_all` | `DraftConfirmAllProposed` |
| `record_merge` | the kernel | **Draft**; params `merge` (string), `conflicts` (integer), `paths` (string, many) | — | the stage (per the matrix); `target.merging` ← `params.merge`, `target.conflicts` ← `params.conflicts` | — | `DraftRecordMerge` |
| `record_checkout` | the kernel | **Draft**; params `content` (string) | — | the stage (per the matrix) | — | `DraftRecordCheckout` |
| `record_confirm_all` | the kernel | **Draft**; params `confirmed` (string, many) | — | the stage (per the matrix) | — | `DraftRecordConfirmAll` |
| `record_evidence` | the kernel | **Commit**; params `strength` (string), `error` (string) | — | the stage (per the matrix); `target.last_evidence` ← `params.strength`, `target.evidence_error` ← `params.error` | — | `CommitRecordEvidence` |
| `cite_evidence` | owner | **Commit**; params `kind` (one of interview, source, check, event, approval-run), `ref` (string) | `not-approved`: An approved commit is settled; cite evidence before approving it. | the stage (per the matrix) | kernel `cite_evidence` → `record_evidence` | `CommitCiteEvidence` |

## Transitions

For each stage: may the action happen, and where does it lead? A missing cell is undecided; nothing is ever silently allowed.

### Answer (`stage`)

| stage | `record_answer_ref` |
| --- | --- |
| `recorded` | → `recorded` |

### Commit (`stage`)

| stage | `check_commit` | `record_check` | `approve_commit` | `record_approval` | `deliver` | `record_evidence` | `cite_evidence` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `recorded` | → `recorded` | → `recorded` | → `recorded` | → `recorded` | → `recorded` | → `recorded` | → `recorded` |

### DecisionRequest (`stage`)

| stage | `decide` |
| --- | --- |
| `open` | → `decided` |
| `decided` | denied: Already decided; a new decision needs a new request. |

### Draft (`stage`)

| stage | `commit_draft` | `next_questions` | `record_questions` | `search` | `record_search` | `skip_stage` | `record_skip` | `merge_main` | `checkout_commit` | `confirm_all_proposed` | `record_merge` | `record_checkout` | `record_confirm_all` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `open` | → `open` | → `open` | → `open` | → `open` | → `open` | → `open` | → `open` | → `open` | → `open` | → `open` | → `open` | → `open` | → `open` |

### Element (`review`)

| stage | `confirm_element` | `mark_unknown` | `record_proposal` | `record_confirmation` |
| --- | --- | --- | --- | --- |
| `proposed` | → `confirmed` | → `unknown` | → `proposed` | n/a |
| `unknown` | → `confirmed` | n/a | n/a | n/a |
| `confirmed` | n/a | denied: A confirmed element changes by a new proposal and a new commit, not by marking it unknown. | n/a | → `confirmed` |

### Source (`stage`)

| stage | `fetch_source` | `record_fetch` |
| --- | --- | --- |
| `added` | → `added` | → `fetched` |
| `fetched` | denied: A link is fetched once into a snapshot; add a new source to read it again. | n/a |

## Always true (invariants)

- **approved-commits-passed-their-checks** on Commit: An approved commit passed its change check.
- **decided-requests-record-the-choice** on DecisionRequest: A decided request records what was chosen.
- **fetched-sources-have-a-snapshot** on Source: A fetched source has the hash of its snapshot.
- **elements-cite-a-source** on Element: Every element cites where it came from.

## Examples and scenarios

- 12 example object(s): Source `S-code`, Source `S-docs`, Question `Q1`, Answer `A1`, Element `E1`, Element `E2`, Element `E3`, DecisionRequest `DR1`, Draft `D1`, Commit `C1`, Commit `C2`, Commit `C3`
- scenario `approve-only-after-a-passing-check`: 5 step(s)
- scenario `a-confirmed-element-is-not-unknown-again`: 2 step(s)
- scenario `a-decision-is-taken-once`: 2 step(s)
- scenario `a-link-is-fetched-once`: 1 step(s)

## Handoffs

- `deliver_approved_commit`: after `deliver`, calls delivery.`request_delivery`

## How to work in this domain

Generated from the actions, their actors, the matrix and the kernel calls: for each thing, how it comes to exist, then what can happen in each stage and who does it. Steps marked **a person only** are never taken by an agent.

### Answer

- **answer_question** by `owner`, `expert` → `recorded`. Then starts kernel `record_answer`, answered by `record_answer_ref`. Run: `toprope-run --domain authoring.domain.yaml answer_question NEW_ID --question QUESTION --words WORDS --decisions DECISIONS`

**In `recorded`:**

- **record_answer_ref** by the kernel, automatically (a reply)

### Commit

- **record_commit** by the kernel, automatically (a reply) → `recorded`

**In `recorded`:**

- **check_commit** by `owner`. Needs: An approved commit passed its check; check a new commit instead. Then starts kernel `change_check`, answered by `record_check`. Run: `toprope-run --domain authoring.domain.yaml check_commit ID`
- **record_check** by the kernel, automatically (a reply). Needs: An approved commit's check is settled; a late result is not recorded
- **approve_commit** by `owner` — **a person only** — recorded as a decision. Needs: Run the change check, and approve only a commit that passes it. Already approved; approve a newer commit. Then starts kernel `approve_commit`, answered by `record_approval`. Run: `toprope-run --domain authoring.domain.yaml approve_commit ID`
- **record_approval** by the kernel, automatically (a reply). Needs: A commit is recorded as approved only if its change check passed
- **deliver** by `owner`. Needs: Only an approved commit is delivered. Then hands over to delivery.`request_delivery`. Run: `toprope-run --domain authoring.domain.yaml deliver ID --environment ENVIRONMENT`
- **record_evidence** by the kernel, automatically (a reply)
- **cite_evidence** by `owner`. Needs: An approved commit is settled; cite evidence before approving it. Then starts kernel `cite_evidence`, answered by `record_evidence`. Run: `toprope-run --domain authoring.domain.yaml cite_evidence ID --kind KIND --ref REF`

### DecisionRequest

- **request_decision** by `owner` → `open`. Run: `toprope-run --domain authoring.domain.yaml request_decision NEW_ID --element ELEMENT --subject SUBJECT --grounds GROUNDS --recommendation RECOMMENDATION`

**In `open`:**

- **decide** by `owner` — **a person only** — recorded as a decision → `decided`. Run: `toprope-run --domain authoring.domain.yaml decide ID --choice CHOICE`

**In `decided`:** nothing more happens (final).

### Draft

- **open_draft** by `owner` → `open`. Run: `toprope-run --domain authoring.domain.yaml open_draft NEW_ID --domain-id DOMAIN_ID --declaration DECLARATION --branch BRANCH`

**In `open`:**

- **commit_draft** by `owner`. Then starts kernel `commit`, answered by `record_commit`. Run: `toprope-run --domain authoring.domain.yaml commit_draft ID`
- **next_questions** by `owner`. Then starts kernel `stage_questions`, answered by `record_questions`. Run: `toprope-run --domain authoring.domain.yaml next_questions ID`
- **record_questions** by the kernel, automatically (a reply)
- **search** by `owner`. Then starts kernel `search_sources`, answered by `record_search`. Run: `toprope-run --domain authoring.domain.yaml search ID --query QUERY`
- **record_search** by the kernel, automatically (a reply)
- **skip_stage** by `owner` — **a person only**. Then starts kernel `skip_stage`, answered by `record_skip`. Run: `toprope-run --domain authoring.domain.yaml skip_stage ID --stage STAGE --reason REASON`
- **record_skip** by the kernel, automatically (a reply)
- **merge_main** by `owner`. Then starts kernel `merge_main`, answered by `record_merge`. Run: `toprope-run --domain authoring.domain.yaml merge_main ID`
- **checkout_commit** by `owner`. Then starts kernel `checkout`, answered by `record_checkout`. Run: `toprope-run --domain authoring.domain.yaml checkout_commit ID --commit COMMIT`
- **confirm_all_proposed** by `owner` — **a person only**. Then starts kernel `confirm_element`, answered by `record_confirm_all`. Run: `toprope-run --domain authoring.domain.yaml confirm_all_proposed ID`
- **record_merge** by the kernel, automatically (a reply)
- **record_checkout** by the kernel, automatically (a reply)
- **record_confirm_all** by the kernel, automatically (a reply)

### Element

- **propose_element** by `owner` → `proposed`. Then starts kernel `propose_element`, answered by `record_proposal`. Run: `toprope-run --domain authoring.domain.yaml propose_element NEW_ID --path PATH --origin ORIGIN --cites CITES --value VALUE`

**In `proposed`:**

- **confirm_element** by `owner` — **a person only** → `confirmed`. Then starts kernel `confirm_element`, answered by `record_confirmation`. Run: `toprope-run --domain authoring.domain.yaml confirm_element ID`
- **mark_unknown** by `owner`, `expert` → `unknown`. Run: `toprope-run --domain authoring.domain.yaml mark_unknown ID`
- **record_proposal** by the kernel, automatically (a reply)

**In `confirmed`:**

- **record_confirmation** by the kernel, automatically (a reply)

**In `unknown`:**

- **confirm_element** by `owner` — **a person only** → `confirmed`. Then starts kernel `confirm_element`, answered by `record_confirmation`. Run: `toprope-run --domain authoring.domain.yaml confirm_element ID`

### Source

- **add_source** by `owner` → `added`. Run: `toprope-run --domain authoring.domain.yaml add_source NEW_ID --kind KIND --path PATH`

**In `added`:**

- **fetch_source** by `owner`. Then starts kernel `fetch_source`, answered by `record_fetch`. Run: `toprope-run --domain authoring.domain.yaml fetch_source ID`
- **record_fetch** by the kernel, automatically (a reply) → `fetched`

**In `fetched`:** nothing more happens (final).

### Other actions

- **ask_question** by `owner`, `expert`. Run: `toprope-run --domain authoring.domain.yaml ask_question NEW_ID --stage STAGE --text TEXT`

## What is generated

- **Command line** `toprope-run --domain authoring.domain.yaml ...`: one subcommand per action, with the same rules as every other surface (ADR-0036), plus `get`, `history`, `allowed` and `guide`.
- **MCP server** `toprope:authoring`: one tool per action (35), plus `get_object`, `history`, `attempts`, `allowed_actions`, `describe_domain`, `world_map` and `how_to_reach`. Kernel replies (`record_fetch`, `record_commit`, `record_check`, `record_approval`, `record_proposal`, `record_confirmation`, `record_answer_ref`, `record_questions`, `record_search`, `record_skip`, `record_merge`, `record_checkout`, `record_confirm_all`, `record_evidence`) are tools too, but only the kernel may take them.
- **Events**: one per action (`AnswerCreated`, `AnswerRecordAnswerRef`, `CommitApproveCommit`, `CommitCheckCommit`, `CommitCiteEvidence`, `CommitCreated`, `CommitDeliver`, `CommitRecordApproval`, `CommitRecordCheck`, `CommitRecordEvidence`, `DecisionRequestCreated`, `DecisionRequestDecide`, `DraftCheckoutCommit`, `DraftCommitDraft`, `DraftConfirmAllProposed`, `DraftCreated`, `DraftMergeMain`, `DraftNextQuestions`, `DraftRecordCheckout`, `DraftRecordConfirmAll`, `DraftRecordMerge`, `DraftRecordQuestions`, `DraftRecordSearch`, `DraftRecordSkip`, `DraftSearch`, `DraftSkipStage`, `ElementConfirmElement`, `ElementCreated`, `ElementMarkUnknown`, `ElementRecordConfirmation`, `ElementRecordProposal`, `QuestionCreated`, `SourceCreated`, `SourceFetchSource`, `SourceRecordFetch`); the current state is the events replayed in order.
- **World map** (`world-map.json`): every object, link, stage and (stage, action) edge.
- **Harness**: passes; decided cells covered per level: model 117/117, execution 117/117; 0 finding(s).
