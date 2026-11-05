# Domain guide: `authoring` (version 1)

_Generated from the declaration at build time. Do not edit: change the declaration._

## Purpose

A domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code.

**Success metric:** human minutes from an owner's intent to a confirmed, compiled domain version (down is better)

> Domain owners now turn the workflow in their heads into a declared, checked domain without writing code. Every change shows what it breaks before anything is deployed.

## People and things

**Roles:** `owner` (ana), `expert` (eli). Agents act only on a person's behalf, with a grant.

- **Answer**: The owner's answer, in their words; its decisions become proposed elements.
  - facts: `words` (string)
- **Commit**: An immutable snapshot of the working copy on a branch. Stages: `recorded` (starts `recorded`).
  - facts: `seq` (integer), `content` (string), `branch` (string), `author` (string, optional), `message` (string, optional), `interface` (string), `domain_id` (string), `checks_passed` (boolean, optional), `failing` (string, optional), `approved` (boolean, optional), `main` (string, optional)
- **DecisionRequest**: A decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox. Stages: `open`, `decided` (starts `open`).
  - facts: `subject` (string), `grounds` (string), `recommendation` (string), `choice` (string, optional)
- **Draft**: The working copy of a domain's declaration on a branch: what a commit snapshots. Stages: `open` (starts `open`).
  - facts: `domain_id` (string), `declaration` (string), `branch` (string)
- **Element**: One part of the draft declaration (an object, action, cell, invariant...), proposed by an agent or confirmed by a person. Stages: `proposed`, `unknown`, `confirmed` (starts `proposed`).
  - facts: `path` (string)
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
| `ask_question` | owner | creates **Question**; params `stage` (string), `text` (string) | — | — | — | `QuestionCreated` |
| `answer_question` | owner, expert | creates **Answer**; params `question` (a Question), `words` (string) | — | — | — | `AnswerCreated` |
| `propose_element` | owner | creates **Element**; params `path` (string), `origin` (a Source) | — | — | — | `ElementCreated` |
| `confirm_element` 🔒 | owner | **Element** | — | the stage (per the matrix) | — | `ElementConfirmElement` |
| `mark_unknown` | owner, expert | **Element** | — | the stage (per the matrix) | — | `ElementMarkUnknown` |
| `request_decision` | owner | creates **DecisionRequest**; params `element` (a Element), `subject` (string), `grounds` (string), `recommendation` (string) | — | — | — | `DecisionRequestCreated` |
| `decide` 🔒 📝 | owner | **DecisionRequest**; params `choice` (string) | — | the stage (per the matrix); `target.choice` ← `params.choice` | — | `DecisionRequestDecide` |
| `commit_draft` | owner | **Draft** | — | the stage (per the matrix) | kernel `commit` → `record_commit` | `DraftCommitDraft` |
| `record_commit` | the kernel | creates **Commit**; params `seq` (integer), `content` (string), `interface` (string) | — | — | — | `CommitCreated` |
| `check_commit` | owner | **Commit** | — | the stage (per the matrix) | kernel `change_check` → `record_check` | `CommitCheckCommit` |
| `record_check` | the kernel | **Commit**; params `passed` (boolean), `summary` (string) | — | the stage (per the matrix); `target.checks_passed` ← `params.passed`, `target.failing` ← `params.summary` | — | `CommitRecordCheck` |
| `approve_commit` 🔒 📝 | owner | **Commit** | `checks-pass`: Run the change check, and approve only a commit that passes it.; `not-approved`: Already approved; approve a newer commit. | the stage (per the matrix) | kernel `approve_commit` → `record_approval` | `CommitApproveCommit` |
| `record_approval` | the kernel | **Commit**; params `approved` (boolean), `main` (string) | — | the stage (per the matrix); `target.approved` ← `params.approved`, `target.main` ← `params.main` | — | `CommitRecordApproval` |

## Transitions

For each stage: may the action happen, and where does it lead? A missing cell is undecided; nothing is ever silently allowed.

### Commit (`stage`)

| stage | `check_commit` | `record_check` | `approve_commit` | `record_approval` |
| --- | --- | --- | --- | --- |
| `recorded` | → `recorded` | → `recorded` | → `recorded` | → `recorded` |

### DecisionRequest (`stage`)

| stage | `decide` |
| --- | --- |
| `open` | → `decided` |
| `decided` | denied: Already decided; a new decision needs a new request. |

### Draft (`stage`)

| stage | `commit_draft` |
| --- | --- |
| `open` | → `open` |

### Element (`review`)

| stage | `confirm_element` | `mark_unknown` |
| --- | --- | --- |
| `proposed` | → `confirmed` | → `unknown` |
| `unknown` | → `confirmed` | n/a |
| `confirmed` | n/a | denied: A confirmed element changes by a new proposal and a new commit, not by marking it unknown. |

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

- 11 example object(s): Source `S-code`, Source `S-docs`, Question `Q1`, Answer `A1`, Element `E1`, Element `E2`, Element `E3`, DecisionRequest `DR1`, Draft `D1`, Commit `C1`, Commit `C2`
- scenario `approve-only-after-a-passing-check`: 5 step(s)
- scenario `a-confirmed-element-is-not-unknown-again`: 2 step(s)
- scenario `a-decision-is-taken-once`: 2 step(s)
- scenario `a-link-is-fetched-once`: 1 step(s)

## What is generated

- **MCP server** `toprope:authoring`: one tool per action (16), plus `get_object`, `history`, `attempts`, `allowed_actions`, `describe_domain`, `world_map` and `how_to_reach`. Kernel replies (`record_fetch`, `record_commit`, `record_check`, `record_approval`) are tools too, but only the kernel may take them.
- **Events**: one per action (`AnswerCreated`, `CommitApproveCommit`, `CommitCheckCommit`, `CommitCreated`, `CommitRecordApproval`, `CommitRecordCheck`, `DecisionRequestCreated`, `DecisionRequestDecide`, `DraftCommitDraft`, `ElementConfirmElement`, `ElementCreated`, `ElementMarkUnknown`, `QuestionCreated`, `SourceCreated`, `SourceFetchSource`, `SourceRecordFetch`); the current state is the events replayed in order.
- **World map** (`world-map.json`): every object, link, stage and (stage, action) edge.
- **Harness**: passes; decided cells covered per level: model 51/51, execution 51/51, mcp 51/51; 0 finding(s).
