# SKILL: working in the Authoring and Delivery domains (composition `toprope-self`, version 1)

The composition `toprope-self` (version 1) has two members: `authoring` (interface 1) and `delivery` (interface 1). One wire joins them: `authoring.deliver_approved_commit` → `delivery.request_delivery`.

## Authoring (domain version 4)

**Purpose.** Problem: a domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code. Success metric: "human minutes from an owner's intent to a confirmed, compiled domain version" (direction: down). Announcement: "Domain owners now turn the workflow in their heads into a declared, checked domain without writing code. Every change shows what it breaks before anything is deployed."

### Roles
- `owner` (world actor: ana)
- `expert` (world actor: eli)
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
| review | enum: proposed, confirmed, unknown (initial: proposed) | no |
| value | string | yes |
| cites | string | no |
| issues | integer | yes |
| issue_summary | string | yes |

**DecisionRequest** — a decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox.
| Property | Type | Optional |
|---|---|---|
| subject | string | no |
| grounds | string | no |
| recommendation | string | no |
| deadline | string (a date, YYYY-MM-DD) | yes |
| stage | enum: open, decided (initial: open) | no |
| choice | string | yes |

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
| approved | boolean | yes |
| main | string | yes |
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
| propose_element | owner | creates Element | path (string); origin (reference to Source); cites (string); value (string) | Kernel call `propose_element` with path = target.path, value = target.value, source = target.cites; reply action `record_proposal`. |
| confirm_element | owner | target Element | none | **requires: human.** Kernel call `confirm_element` with paths = target.path, approver = actor.id; reply action `record_confirmation`. |
| mark_unknown | owner, expert | target Element | none | none declared |
| request_decision | owner | creates DecisionRequest | element (reference to Element); subject (string); grounds (string); recommendation (string); deadline (string, a date YYYY-MM-DD, optional) | none declared |
| decide | owner | target DecisionRequest | choice (string) | **requires: human; records a decision.** Sets target.choice = params.choice. |
| commit_draft | owner | target Draft | none | Kernel call `commit` with declaration = target.declaration; reply action `record_commit`. |
| record_commit | external:kernel | creates Commit | seq (integer); content (string); interface (string); domain (string); branch (string); author (string) | Sets target.domain_id = params.domain. |
| check_commit | owner | target Commit | none | Kernel call `change_check` with domain = target.domain_id, commit = target.id; reply action `record_check`. |
| record_check | external:kernel | target Commit | passed (boolean); summary (string) | Sets target.checks_passed = params.passed and target.failing = params.summary. |
| approve_commit | owner | target Commit | none | **requires: human; records a decision.** Merge it into main and tag it. Kernel call `approve_commit` with domain = target.domain_id, commit = target.id, approver = actor.id; reply action `record_approval`. |
| record_approval | external:kernel | target Commit | approved (boolean); main (string) | Sets target.approved = params.approved and target.main = params.main. |
| deliver | owner | target Commit | environment (enum: local) | No effects declared; it hands off to Delivery (see Handoff). |
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
- propose_element: Propose a draft element that cites where it came from.
- confirm_element: Confirm a drafted element. Only a person confirms.
- mark_unknown: Mark an element as not known yet, instead of guessing.
- request_decision: Ask the owner for a decision only a person may take, with grounds and a recommendation, and optionally a deadline date that the owner sees when the decision is asked.
- decide: Decide a requested decision.
- commit_draft: Snapshot the working copy as an immutable commit.
- record_commit: Record the commit the kernel made.
- check_commit: Run the change check on a commit.
- record_check: Record the change check's result on the commit.
- approve_commit: Approve a commit: merge it into main and tag it. Only a person approves.
- record_approval: Record the approval and what main points to.
- deliver: Ask Delivery to deliver an approved commit to an environment.
- record_proposal: Record whether the drafted element was written into the working copy.
- record_confirmation: Record that the working copy holds the element as confirmed.
- record_answer_ref: Record where the answer is in the interview log, so elements can cite it.
- next_questions: Ask for the current stage's bundle of questions.
- record_questions: Record the current stage and its bundle.
- search: Search the sources (redacted; local-only never served); the result is on record.
- record_search: Record which source chunks a search returned.
- skip_stage: Say an optional stage has nothing, in the owner's words.
- record_skip: Record that the stage was skipped.
- open_draft: Open a working copy of a domain's declaration on a branch, so it can be interviewed, committed and checked.
- merge_main: Bring main into the branch's working copy and list the conflicts to resolve; the next commit records both parents.
- checkout_commit: Load a commit into the working copy, to revert to it or build on it; committing it makes a new commit.
- confirm_all_proposed: Confirm every element still proposed in the working copy, as right.
- record_merge: Record the merge in progress and how many conflicts it left.
- record_checkout: Record that the working copy holds the commit's content.
- record_confirm_all: Record which elements were confirmed.

Actions that only a person may take (`requires: human`): confirm_element, decide, approve_commit, skip_stage, confirm_all_proposed.
Actions that record a decision: decide, approve_commit.

### Preconditions (named; separate from the transition tables)
| Action | Id | Check | Reason |
|---|---|---|---|
| check_commit | not-approved | `target.approved != true` | An approved commit passed its check; check a new commit instead. |
| approve_commit | checks-pass | `target.checks_passed == true` | Run the change check, and approve only a commit that passes it. |
| approve_commit | not-approved | `target.approved != true` | Already approved; approve a newer commit. |
| record_approval | approved-only-if-checked | `params.approved != true or target.checks_passed == true` | A commit is recorded as approved only if its change check passed. |
| deliver | approved | `target.approved == true` | Only an approved commit is delivered. |

### Transitions (state field and initial state; cell = result of the action in that state)

**Source** (field stage, initial added)
| State | fetch_source | record_fetch |
|---|---|---|
| added | to added | to fetched |
| fetched | deny: "A link is fetched once into a snapshot; add a new source to read it again." | n/a |

**Element** (field review, initial proposed)
| State | confirm_element | mark_unknown | record_proposal | record_confirmation |
|---|---|---|---|---|
| proposed | to confirmed | to unknown | to proposed | n/a |
| unknown | to confirmed | n/a | n/a | n/a |
| confirmed | n/a | deny: "A confirmed element changes by a new proposal and a new commit, not by marking it unknown." | n/a | to confirmed |

**DecisionRequest** (field stage, initial open)
| State | decide |
|---|---|
| open | to decided |
| decided | deny: "Already decided; a new decision needs a new request." |

**Draft** (field stage, initial open). In state open every one of these actions goes to open: commit_draft, next_questions, record_questions, search, record_search, skip_stage, record_skip, merge_main, record_merge, checkout_commit, record_checkout, confirm_all_proposed, record_confirm_all.

**Commit** (field stage, initial recorded). In state recorded every one of these goes to recorded: check_commit, record_check, approve_commit, record_approval, deliver.

**Answer** (field stage, initial recorded). In state recorded: record_answer_ref goes to recorded.

### Invariants
| Id | On | Check | Reason |
|---|---|---|---|
| approved-commits-passed-their-checks | Commit | `target.approved != true or target.checks_passed == true` | An approved commit passed its change check. |
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
- `system` takes request_delivery; `external:kernel` takes the record_* actions.

### Objects

**DeliveryRequest** — a request to deliver an approved commit of a domain, handed off by Authoring.
| Property | Type | Optional |
|---|---|---|
| domain_id | string | no |
| commit | string | no |
| interface | string | no |
| environment | string | no |
| approver | string | no |
| build | string | yes |
| harness_ok | boolean | yes |
| deployed | boolean | yes |
| refusal | string | yes |
| verified | boolean | yes |
| stage | enum: requested, previewing, previewed, deploying, done, verified (initial: requested) | no |

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
| request_delivery | system | creates DeliveryRequest | domain_id, commit, interface, environment, approver (all string) | none declared |
| preview | approver | target DeliveryRequest | none | Kernel call `preview` with domain = target.domain_id, commit = target.commit; reply action `record_build`. |
| record_build | external:kernel | target DeliveryRequest | build (string); harness_ok (boolean) | Sets target.build = params.build and target.harness_ok = params.harness_ok. |
| deploy | approver | target DeliveryRequest | none | **requires: human; records a decision.** Kernel call `deploy` with domain = target.domain_id, commit = target.commit, approver = actor.id; reply action `record_deployment`. |
| record_deployment | external:kernel | target DeliveryRequest | deployed (boolean); error (string) | Sets target.deployed = params.deployed and target.refusal = params.error. |
| verify | approver | target DeliveryRequest | verified (boolean) | **requires: human.** Sets target.verified = params.verified. |

Descriptions:
- request_delivery: Receive a request to deliver an approved commit, handed off by Authoring.
- preview: Build the commit and run its harness, before anything is deployed.
- record_build: Record the build and its harness result.
- deploy: Deploy the commit, under the fixed floor. Only a person deploys.
- record_deployment: Record whether the deploy happened, or which floor rule refused it.
- verify: Confirm the deployed domain works in use (the probes).

Only a person may take: deploy, verify. Records a decision: deploy.

### Preconditions
| Action | Id | Check | Reason |
|---|---|---|---|
| deploy | harness-passed | `target.harness_ok == true` | Deploy only a build whose harness passed. |
| verify | deployed | `target.deployed == true` | Only a deployment that happened can be verified. |

### Transitions: DeliveryRequest (field stage, initial requested)
| State | preview | record_build | deploy | record_deployment | verify |
|---|---|---|---|---|---|
| requested | to previewing | n/a | deny: "Preview it first." | n/a | n/a |
| previewing | deny: "A preview is running." | to previewed | deny: "The preview has not finished." | n/a | n/a |
| previewed | to previewing | n/a | to deploying | n/a | n/a |
| deploying | deny: "A deploy is running." | n/a | deny: "A deploy is running." | to done | n/a |
| done | to previewing | n/a | to deploying | n/a | to verified |
| verified | n/a | n/a | n/a | n/a | deny: "Already verified." |

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

### World (fixtures)
Actor: approver ana.
- Environment ENV-local (name local).
- R1: domain_id authoring, commit 2-c3d4, interface 1.1.0, environment local, approver ana, stage requested.
- R2: authoring, commit 3-e5f6, interface 1.1.0, local, ana, stage previewed, build b2, harness_ok false.
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
- Handoff target: `target.domain_id + ':' + target.id + ':' + params.environment`.
- What the receiver needs: `request_delivery` takes domain_id, commit, interface, environment and approver (all strings) and creates a DeliveryRequest.
