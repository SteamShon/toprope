# SKILL: working in the Authoring and Delivery domains (composition `toprope-self`, version 1)

The composition `toprope-self` (version 1) has two members: `authoring` (interface 1) and `delivery` (interface 1). One wire joins them: `authoring.deliver_approved_commit` → `delivery.request_delivery`.

## Authoring (domain version 4)

**Purpose.** Problem: a domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code. Success metric: "human minutes from an owner's intent to a confirmed, compiled domain version" (direction: down). Announcement: "Domain owners now turn the workflow in their heads into a declared, checked domain without writing code. Every change shows what it breaks before anything is deployed."

### Roles
- `owner` (world actor: ana)
- `expert` (world actor: eli)
- `deputy` is a person the owner names (see `name_deputy`) to approve commits while the owner is away. The deputy takes only `approve_commit` (no world actor).
- `agent` takes only `confirm_wording_fix` and `decide` (no world actor). The agent takes `decide` only when the owner has said so in chat (see precondition `owner-said-so`).
- `external:kernel` also acts, taking only the `record_*` actions and none of the owner/expert actions.

### Objects

**Source** — where raw material lives: code, records, transcripts or the interview log.
| Property | Type | Optional |
|---|---|---|
| kind | enum: repository, records, transcripts, interview-log | no |
| path | string | no |
| local_only | boolean | no |
| sha256 | string | yes |
| stage | enum: added, fetched (initial: added) | no |

**Question** — a question in a stage's bundle, for the owner to answer.
| Property | Type | Optional |
|---|---|---|
| stage | string | no |
| text | string | no |

**Answer** — the owner's answer, in their words; its decisions become proposed elements.
| Property | Type | Optional |
|---|---|---|
| words | string | no |
| decisions | string | no |
| ref | string | yes |
| stage | enum: recorded (initial: recorded) | no |

**Element** — one part of the draft declaration (an object, action, cell, invariant...), proposed by an agent or confirmed by a person.
| Property | Type | Optional |
|---|---|---|
| path | string | no |
| review | enum: proposed, confirmed, unknown, withdrawn (initial: proposed) | no |
| value | string | yes |
| cites | string | no |
| issues | integer | yes |
| issue_summary | string | yes |
| wording_only | boolean | yes |
| confirm_reason | string | yes |
| drafted_by | string | yes |

**DecisionRequest** — a decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox.
| Property | Type | Optional |
|---|---|---|
| subject | string | no |
| grounds | string | no |
| recommendation | string | no |
| deadline | string (a date, YYYY-MM-DD) | yes |
| stage | enum: open, decided (initial: open) | no |
| choice | string | yes |

**Deputy** — a person the owner has named to approve commits while the owner is away.
| Property | Type | Optional |
|---|---|---|
| person | string | no |
| stage | enum: named, ended (initial: named) | no |

**Commit** — an immutable snapshot of the working copy on a branch.
| Property | Type | Optional |
|---|---|---|
| seq | integer | no |
| content | string | no |
| branch | string | no |
| author | string | yes |
| message | string | yes |
| interface | string | no |
| domain_id | string | no |
| checks_passed | boolean | yes |
| failing | string | yes |
| checked_at | timestamp | yes |
| approved | boolean | yes |
| wording_only | boolean | yes |
| main | string | yes |
| release_name | string | yes |
| stage | enum: recorded (initial: recorded) | no |

**Draft** — the working copy of a domain's declaration on a branch: what a commit snapshots.
| Property | Type | Optional |
|---|---|---|
| domain_id | string | no |
| declaration | string | no |
| branch | string | no |
| stage | enum: open (initial: open) | no |
| current_stage | string | yes |
| bundle | string | yes |
| merging | string | yes |
| conflicts | integer | yes |

### Links
| Link | From → To | Cardinality | Required |
|---|---|---|---|
| question | Answer → Question | many-to-one | yes |
| element | DecisionRequest → Element | many-to-one | no |
| parents | Commit → Commit | many-to-many | no |
| origin | Element → Source | many-to-one | no |

### Actions

"Kernel call" means a kernel service call, with the arguments and the action that receives the reply.

| Action | Who | Target / creates | Params | Effects |
|---|---|---|---|---|
| add_source | owner | creates Source | kind (enum: repository, records, transcripts, interview-log); path (string); local_only (boolean, optional) | none declared |
| fetch_source | owner | target Source | none | Kernel call `fetch_source` with source = target.id; reply action `record_fetch`. |
| record_fetch | external:kernel | target Source | sha256 (string) | Sets target.sha256 = params.sha256. |
| ask_question | owner, expert | creates Question | stage (string); text (string) | none declared |
| answer_question | owner, expert | creates Answer | question (reference to Question); words (string); decisions (string) | Kernel call `record_answer` with question = target.question.text, answer = target.words, decisions = target.decisions; reply action `record_answer_ref`. |
| propose_element | owner | creates Element | path (string); origin (reference to Source); cites (string); value (string); drafted_by (string); wording_only (boolean, optional) | Sets target.wording_only = params.wording_only and target.drafted_by = params.drafted_by. Kernel call `propose_element` with path = target.path, value = target.value, source = target.cites; reply action `record_proposal`. |
| confirm_element | owner | target Element | reason (string) | **requires: human.** Sets target.confirm_reason = params.reason. Kernel call `confirm_element` with paths = target.path, approver = actor.id; reply action `record_confirmation`. |
| confirm_wording_fix | agent | target Element | none | Kernel call `confirm_element` with paths = target.path, approver = actor.id; reply action `record_confirmation`. Does not require a human, but only for an element whose change is wording only (precondition `wording-only`). |
| mark_unknown | owner, expert | target Element | none | none declared |
| withdraw_element | owner | target Element | none | none declared |
| request_decision | owner | creates DecisionRequest | element (reference to Element); subject (string); grounds (string); recommendation (string); deadline (string, a date YYYY-MM-DD, optional) | none declared |
| decide | owner, agent | target DecisionRequest | choice (string); owner_words (string, optional; required when the agent takes it) | **records a decision; requires: human, except when the agent takes it on the owner's word in chat (see `owner-said-so`).** Sets target.choice = params.choice. |
| commit_draft | owner | target Draft | none | Kernel call `commit` with declaration = target.declaration; reply action `record_commit`. |
| record_commit | external:kernel | creates Commit | seq (integer); content (string); interface (string); domain (string); branch (string); author (string) | Sets target.domain_id = params.domain. |
| check_commit | owner | target Commit | none | Kernel call `change_check` with domain = target.domain_id, commit = target.id; reply action `record_check`. |
| record_check | external:kernel | target Commit | passed (boolean); summary (string) | Sets target.checks_passed = params.passed, target.failing = params.summary and target.checked_at = the time the result is recorded. |
| name_deputy | owner | creates Deputy | person (string) | none declared |
| end_deputy | owner | target Deputy | none | none declared |
| approve_commit | owner, deputy | target Commit | wording_only (boolean, optional) | **requires: human; records a decision.** Sets target.wording_only = params.wording_only. Merge it into main and tag it. Kernel call `approve_commit` with domain = target.domain_id, commit = target.id, approver = actor.id; reply action `record_approval`. |
| record_approval | external:kernel | target Commit | approved (boolean); main (string) | Sets target.approved = params.approved and target.main = params.main. |
| name_release | owner | target Commit | release_name (string) | Sets target.release_name = params.release_name. |
| deliver | owner | target Commit | environment (enum: local, staging) | No effects declared; it hands off to Delivery (see Handoff). |
| record_proposal | external:kernel | target Element | issues (integer); summary (string) | Sets target.issues = params.issues and target.issue_summary = params.summary. |
| record_confirmation | external:kernel | target Element | confirmed (list of string) | none declared |
| record_answer_ref | external:kernel | target Answer | ref (string) | Sets target.ref = params.ref. |
| next_questions | owner | target Draft | none | Kernel call `stage_questions` with no arguments; reply action `record_questions`. |
| record_questions | external:kernel | target Draft | stage (string); bundle (string); questions (list of string) | Sets target.current_stage = params.stage and target.bundle = params.bundle. |
| search | owner | target Draft | query (string) | Kernel call `search_sources` with query = params.query; reply action `record_search`. |
| record_search | external:kernel | target Draft | refs (list of string) | none declared |
| skip_stage | owner | target Draft | stage (string); reason (string) | **requires: human.** Kernel call `skip_stage` with stage = params.stage, reason = params.reason; reply action `record_skip`. |
| record_skip | external:kernel | target Draft | skipped (boolean) | none declared |
| open_draft | owner | creates Draft | domain_id (string); declaration (string); branch (string) | none declared |
| merge_main | owner | target Draft | none | Kernel call `merge_main` with domain = target.domain_id, branch = target.branch, declaration = target.declaration; reply action `record_merge`. |
| checkout_commit | owner | target Draft | commit (string) | Kernel call `checkout` with domain = target.domain_id, commit = params.commit, declaration = target.declaration; reply action `record_checkout`. |
| confirm_all_proposed | owner | target Draft | none | **requires: human.** Kernel call `confirm_element` with paths = 'all' (the literal text `'all'`), approver = actor.id; reply action `record_confirm_all`. |
| record_merge | external:kernel | target Draft | merge (string); conflicts (integer); paths (list of string) | Sets target.merging = params.merge and target.conflicts = params.conflicts. |
| record_checkout | external:kernel | target Draft | content (string) | none declared |
| record_confirm_all | external:kernel | target Draft | confirmed (list of string) | none declared |

Action descriptions:
- add_source: Add a source of raw material: code, records, transcripts or the interview log.
- fetch_source: Fetch a link source into a snapshot, once.
- record_fetch: Record the fetched snapshot's hash.
- ask_question: Ask a question of the current stage's bundle.
- answer_question: Answer a question, in the person's own words.
- propose_element: Propose a draft element that cites where it came from, and record which agent drafted it (drafted_by, kept on the element), so the owner can tell which agent drafted a poor element.
- confirm_element: Confirm a drafted element, noting why the owner agreed (kept on the element as confirm_reason). Only a person confirms. For an element about who may approve or deploy, a second person must confirm it as well (see "Permission elements need a second person").
- confirm_wording_fix: Let an agent confirm an element that only fixes wording. Anything beyond wording is still confirmed by a person.
- mark_unknown: Mark an element as not known yet, instead of guessing.
- withdraw_element: Withdraw a proposed element that is simply wrong, so it leaves the draft instead of staying as noise (marking it unknown would keep it visible). Only a proposed element can be withdrawn.
- request_decision: Ask the owner for a decision only a person may take, with grounds and a recommendation, and optionally a deadline date that the owner sees when the decision is asked.
- decide: Decide a requested decision. The owner may decide, or an agent may settle it when the owner has said so in chat; the agent then quotes the owner's chat words in owner_words, and the choice is the one the owner gave.
- commit_draft: Snapshot the working copy as an immutable commit.
- record_commit: Record the commit the kernel made.
- check_commit: Run the change check on a commit.
- record_check: Record the change check's result on the commit, with the time it was recorded. A check counts only while it is less than a day old.
- name_deputy: The owner names a deputy who may approve commits while the owner is away, so changes do not wait for one person's absence.
- end_deputy: The owner ends the deputy's standing to approve.
- approve_commit: Approve a commit: merge it into main and tag it. Only a person approves, and that person is the owner or a deputy the owner has named (and not ended). The deputy's id is recorded as the approver. The checks-pass and not-approved preconditions apply to a deputy exactly as to the owner. A commit whose change is wording only (wording_only = true) may be approved without a passing change check.
- record_approval: Record the approval and what main points to.
- name_release: The owner gives an approved commit a release name, so people can talk about releases instead of commit ids. Only the owner names a release (not a deputy), and only for an approved commit.
- deliver: Ask Delivery to deliver an approved commit to an environment.
- record_proposal: Record whether the drafted element was written into the working copy.
- record_confirmation: Record that the working copy holds the element as confirmed.
- record_answer_ref: Record where the answer is in the interview log, so elements can cite it.
- next_questions: Ask for the current stage's bundle of questions.
- record_questions: Record the current stage and its bundle.
- search: Search the sources (redacted; local-only never served); the result is on record.
- record_search: Record which source chunks a search returned.
- skip_stage: Say a stage has nothing, in the owner's words. The stage may be optional or required: the owner may skip a required stage too, but only by writing why in the reason.
- record_skip: Record that the stage was skipped.
- open_draft: Open a working copy of a domain's declaration on a branch, so it can be interviewed, committed and checked.
- merge_main: Bring main into the branch's working copy and list the conflicts to resolve; the next commit records both parents.
- checkout_commit: Load a commit into the working copy, to revert to it or build on it; committing it makes a new commit.
- confirm_all_proposed: Confirm every element still proposed in the working copy, as right.
- record_merge: Record the merge in progress and how many conflicts it left.
- record_checkout: Record that the working copy holds the commit's content.
- record_confirm_all: Record which elements were confirmed.

**Permission elements need a second person.** An element about who may approve or deploy (for example who takes `approve_commit` or `deploy`, the `requires: human` rule on them, or the roles that hold them) is not final on one person's confirmation. Before treating it as confirmed, ask a second person, different from the first, to confirm it too, and keep both confirmations and their reasons visible. An agent never gives either confirmation: `confirm_wording_fix` does not apply to these elements, even if they are marked wording only. `confirm_all_proposed` does not stand in for the second confirmation either; check these elements one by one. Until the second person has confirmed, say the element is awaiting a second confirmation and do not commit or approve as if it were settled.

Actions that only a person may take (`requires: human`): confirm_element, approve_commit, skip_stage, confirm_all_proposed. `decide` is also a person's action, except that an agent may take it when the owner has said so in chat.
Actions that record a decision: decide, approve_commit.

### Preconditions (named; separate from the transition tables)
| Action | Id | Check | Reason |
|---|---|---|---|
| confirm_wording_fix | wording-only | `target.wording_only == true` | An agent confirms only elements that fix wording; a person confirms the rest. |
| decide | owner-said-so | `actor.role != 'agent' or (exists(params.owner_words) and params.owner_words != '')` | An agent settles a decision request only on the owner's words in chat; quote them in owner_words. |
| check_commit | not-approved | `target.approved != true` | An approved commit passed its check; check a new commit instead. |
| approve_commit | checks-pass | `(target.checks_passed == true and exists(target.checked_at) and now - target.checked_at < 1 day) or params.wording_only == true` | Run the change check, and approve only a commit that passes it with a check less than a day old (a check run long ago may no longer reflect the toolchain; run it again), unless the change is wording only. |
| approve_commit | not-approved | `target.approved != true` | Already approved; approve a newer commit. |
| record_approval | approved-only-if-checked | `params.approved != true or (target.checks_passed == true and exists(target.checked_at) and now - target.checked_at < 1 day) or target.wording_only == true` | A commit is recorded as approved only if its change check passed less than a day ago, or its change is wording only. |
| skip_stage | reason-given | `exists(params.reason) and params.reason != ''` | A stage, required or optional, is skipped only when the owner writes why. |
| deliver | approved | `target.approved == true` | Only an approved commit is delivered. |
| name_release | approved | `target.approved == true` | Only an approved commit is given a release name. |

### Transitions (state field and initial state; cell = result of the action in that state)

**Source** (field stage, initial added)
| State | fetch_source | record_fetch |
|---|---|---|
| added | to added | to fetched |
| fetched | deny: "A link is fetched once into a snapshot; add a new source to read it again." | n/a |

**Element** (field review, initial proposed)
| State | confirm_element | confirm_wording_fix | mark_unknown | withdraw_element | record_proposal | record_confirmation |
|---|---|---|---|---|---|---|
| proposed | to confirmed | to confirmed | to unknown | to withdrawn | to proposed | n/a |
| unknown | to confirmed | to confirmed | n/a | n/a | n/a | n/a |
| confirmed | n/a | n/a | deny: "A confirmed element changes by a new proposal and a new commit, not by marking it unknown." | deny: "A confirmed element changes by a new proposal and a new commit, not by withdrawing it." | n/a | to confirmed |
| withdrawn | n/a | n/a | n/a | n/a | n/a | n/a |

**DecisionRequest** (field stage, initial open)
| State | decide |
|---|---|
| open | to decided |
| decided | deny: "Already decided; a new decision needs a new request." |

**Draft** (field stage, initial open). In state open every one of these actions goes to open: commit_draft, next_questions, record_questions, search, record_search, skip_stage, record_skip, merge_main, record_merge, checkout_commit, record_checkout, confirm_all_proposed, record_confirm_all.

**Deputy** (field stage, initial named). In state named: end_deputy goes to ended. In state ended: end_deputy is denied: "Already ended; name a deputy again to give the standing back."

**Commit** (field stage, initial recorded). In state recorded every one of these goes to recorded: check_commit, record_check, approve_commit, record_approval, name_release, deliver.

**Answer** (field stage, initial recorded). In state recorded: record_answer_ref goes to recorded.

### Invariants
| Id | On | Check | Reason |
|---|---|---|---|
| approved-commits-passed-their-checks | Commit | `target.approved != true or target.checks_passed == true or target.wording_only == true` | An approved commit passed its change check, or its change is wording only. |
| decided-requests-record-the-choice | DecisionRequest | `target.stage != 'decided' or exists(target.choice)` | A decided request records what was chosen. |
| fetched-sources-have-a-snapshot | Source | `target.stage != 'fetched' or exists(target.sha256)` | A fetched source has the hash of its snapshot. |
| elements-cite-a-source | Element | `exists(target.origin)` | Every element cites where it came from. |

### Glossary
- **commit**: An immutable snapshot of the working copy. Every change is a new commit; nothing is edited in place.
- **main**: The protected branch. A commit reaches main only by being approved, and only commits on main are delivered.
- **approval**: A person's decision that merges a commit into main and tags it. It cannot be undone; a newer approved commit supersedes it.
- **element**: One part of a declaration (an object, a link, an action, a cell, an invariant), drafted by an agent and confirmed only by a person.
- **draft**: The working copy of a domain's declaration on a branch: what the next commit will snapshot.
- **change check**: The checks a commit runs before approval: structure, semantics, scenarios, harness, past actions, stranded objects.
- **withdrawn**: A proposed element the owner took back because it was wrong. It leaves the draft; it is not kept as unknown.
- **unknown**: An element marked as not known yet, instead of guessed. It stays visible until someone answers it.

### World (fixtures)
Actors: owner ana; expert eli.
- Sources: S-code (repository, path src/toprope, stage added); S-docs (records, path docs, stage fetched, sha256 5f1c).
- Question Q1 (stage purpose, text "What problem does this domain solve, and for whom?"); Answer A1 (question Q1, words "Owners turn workflows into domains without code.").
- Elements: E1 (path purpose, origin S-docs, review proposed); E2 (path objects.Commit, origin S-code, review confirmed); E3 (path actions.mark_unknown, origin S-docs, review unknown).
- DecisionRequest DR1 (element E1, subject "Which success metric?", grounds "The scope document names two.", recommendation "Human minutes to a confirmed version.", stage open).
- Draft D1 (domain_id authoring, declaration domains/authoring/authoring.domain.yaml, branch work, stage open).
- Commits (all domain_id authoring, branch work, stage recorded): C1 (seq 1, content a1b2, interface 1.0.0, checks_passed true, approved true, main C1); C2 (seq 2, content c3d4, interface 1.1.0, checks_passed false); C3 (seq 3, content e5f6, interface 1.2.0, checks_passed true).

## Delivery (domain version 1)

**Purpose.** Problem: an approved domain version must become working software in an environment, and nothing unverified may reach it. Success metric: "share of approved versions that reach verified-in-use without a manual fix or rollback" (direction: up). Announcement: "Approved domain versions now reach the environment as working software in one step. Nothing that fails its checks or lacks a person's approval gets there."

### Roles
- `approver` (world actor: ana)
- `system` takes request_delivery and auto_deploy; `external:kernel` takes the record_* actions.

### Objects

**DeliveryRequest** — a request to deliver an approved commit of a domain, handed off by Authoring.
| Property | Type | Optional |
|---|---|---|
| domain_id | string | no |
| commit | string | no |
| interface | string | no |
| environment | string | no |
| approver | string | no |
| branch | string | yes |
| replaced_commit | string | yes |
| build | string | yes |
| harness_ok | boolean | yes |
| deployed | boolean | yes |
| refusal | string | yes |
| verified | boolean | yes |
| dry_run | boolean | yes |
| stage | enum: requested, built, deploying, done, verified (initial: requested) | no |

**Environment** — where a domain runs; it points at one deployed commit.
| Property | Type | Optional |
|---|---|---|
| name | string | no |
| current_commit | string | yes |

### Links
None.

### Actions
| Action | Who | Target / creates | Params | Effects |
|---|---|---|---|---|
| request_delivery | system | creates DeliveryRequest | domain_id, commit, interface, environment, approver, branch (all string) | Sets target.branch = params.branch. Sets target.replaced_commit = the current_commit of the Environment named params.environment, as it is when the request is received (left unset if that environment has no current commit). |
| preview | approver | target DeliveryRequest | none | Kernel call `preview` with domain = target.domain_id, commit = target.commit; reply action `record_build`. |
| record_build | external:kernel | target DeliveryRequest | build (string); harness_ok (boolean) | Sets target.build = params.build and target.harness_ok = params.harness_ok. |
| deploy | approver | target DeliveryRequest | none | **requires: human; records a decision.** Kernel call `deploy` with domain = target.domain_id, commit = target.commit, approver = actor.id; reply action `record_deployment`. |
| auto_deploy | system | target DeliveryRequest | none | Runs on its own right after a passing preview (record_build with harness_ok == true), with no one pressing deploy. Kernel call `deploy` with domain = target.domain_id, commit = target.commit, approver = target.approver; reply action `record_deployment`. |
| record_deployment | external:kernel | target DeliveryRequest | deployed (boolean); error (string) | Sets target.deployed = params.deployed and target.refusal = params.error. |
| verify | approver | target DeliveryRequest | verified (boolean) | **requires: human.** If the request has been deployed (target.deployed == true), sets target.verified = params.verified. If it has not been deployed yet (stage requested or built), this is a dry run: sets target.dry_run = params.verified, leaves target.verified unset and the stage unchanged. |

Descriptions:
- request_delivery: Receive a request to deliver an approved commit, handed off by Authoring, with the branch the commit came from. A request that does not say the branch is refused. The request shows, as replaced_commit, the commit the environment was running when the request arrived, so the deployer sees what a deploy would replace.
- preview: Build the commit and run its harness, before anything is deployed.
- record_build: Record the build and its harness result.
- deploy: Deploy the commit, under the fixed floor. Only a person deploys.
- auto_deploy: Deploy the commit on its own after a passing preview, so a passing preview goes out without waiting for someone to press deploy. It is not taken when the harness failed. The deploy floor still applies, and the kernel may refuse (see record_deployment). The manual deploy stays available, e.g. to retry.
- record_deployment: Record whether the deploy happened, or which floor rule refused it.
- verify: Confirm the deployed domain works in use (the probes). Before the deploy (stage requested or built) it records a dry run instead: a rehearsal that is kept on the request as dry_run and never counts as verified.

Only a person may take: deploy, verify. Records a decision: deploy. The exception is auto_deploy, which the system takes after a passing preview.

### Preconditions
| Action | Id | Check | Reason |
|---|---|---|---|
| request_delivery | branch-stated | `exists(params.branch) and params.branch != ''` | A delivery request must say which branch the commit came from. |
| deploy | harness-passed | `target.harness_ok == true` | Deploy only a build whose harness passed. |
| auto_deploy | harness-passed | `target.harness_ok == true` | Deploy only a build whose harness passed. |
| verify | deployed-or-dry-run | `target.deployed == true or target.stage in ['requested', 'built']` | Only a deployment that happened can be verified; before the deploy, verify records a dry run only. |

### Transitions: DeliveryRequest (field stage, initial requested)
| State | preview | record_build | deploy | auto_deploy | record_deployment | verify |
|---|---|---|---|---|---|---|
| requested | to built | n/a | deny: "Preview it first." | n/a | n/a | to requested (dry run) |
| built | to built | to built | to deploying | to deploying | n/a | to built (dry run) |
| deploying | deny: "A deploy is running." | n/a | deny: "A deploy is running." | deny: "A deploy is running." | to done | n/a |
| done | to built | n/a | to deploying | n/a | n/a | to verified |
| verified | n/a | n/a | n/a | n/a | n/a | deny: "Already verified." |

### Invariants
| Id | On | Check | Reason |
|---|---|---|---|
| deployed-builds-passed-their-harness | DeliveryRequest | `target.deployed != true or target.harness_ok == true` | Nothing reaches the environment unless its harness passed. |
| verified-requests-were-deployed | DeliveryRequest | `target.stage != 'verified' or target.deployed == true` | Only a deployment that happened is verified. |
| finished-deploys-record-the-outcome | DeliveryRequest | `target.stage not in ['done', 'verified'] or exists(target.deployed)` | A finished deploy records whether it happened. |
| deploying-builds-passed-their-harness | DeliveryRequest | `target.stage != 'deploying' or target.harness_ok == true` | A deploy starts only from a build whose harness passed. |

### Glossary
- **delivery request**: A request, handed over from Authoring, to put one approved commit of a domain into an environment.
- **preview**: Building a commit and running its harness before anything is deployed; a preview changes no environment.
- **deploy floor**: Rules the kernel enforces on every deploy that no declaration can weaken: approved, on main, not a downgrade, harness passed, a person deploys, nothing stranded.
- **verified**: A deployment a person has checked in use, after it happened.
- **dry run**: A verify taken before the deploy, to rehearse verification. It is recorded as dry_run, does not make the request verified, and changes no stage.

### World (fixtures)
Actor: approver ana.
- Environment ENV-local (name local).
- R1: domain_id authoring, commit 2-c3d4, interface 1.1.0, environment local, approver ana, stage requested.
- R2: authoring, commit 3-e5f6, interface 1.1.0, local, ana, stage built, build b2, harness_ok false.
- R3: authoring, commit 4-a7b8, interface 1.2.0, local, ana, stage done, build b3, harness_ok true, deployed false, refusal "stranded: E-live (state 'ended' is gone)".
- R4: domain_id delivery, commit 5-c9d0, interface 1.0.0, local, ana, stage done, build b4, harness_ok true, deployed true, refusal "" (empty).

## Handoff: Authoring → Delivery

Handoff `deliver_approved_commit`.
- Sent when: Authoring action `deliver` has outcome ok.
- Goes to: domain `delivery`, interface `1.x`, action `request_delivery`.
- Wired in the composition as: `authoring.deliver_approved_commit` → `delivery.request_delivery`.
- Parameters sent:
  | Delivery param | Value from Authoring |
  |---|---|
  | domain_id | target.domain_id |
  | commit | target.id |
  | interface | target.interface |
  | environment | params.environment |
  | approver | actor.id |
  | branch | target.branch |
- Handoff target: `target.domain_id + ':' + target.id + ':' + params.environment`.
- What the receiver needs: `request_delivery` takes domain_id, commit, interface, environment, approver and branch (all strings) and creates a DeliveryRequest; it refuses a request whose branch is missing or empty (precondition `branch-stated`).
