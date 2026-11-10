# SKILL: the Authoring and Delivery domains (composition toprope-self)

Composition `toprope-self`, version 1. Members: `authoring` (declaration authoring/authoring.domain.yaml, interface 1) and `delivery` (declaration delivery/delivery.domain.yaml, interface 1). Wiring: `authoring.deliver_approved_commit` → `delivery.request_delivery`. Authoring declaration version 12; Delivery declaration version 6.

## Authoring

### Purpose
- Problem: A domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code.
- Success metric: "human minutes from an owner's intent to a confirmed, compiled domain version"; direction: down.
- Announcement: Domain owners now turn the workflow in their heads into a declared, checked domain without writing code. Every change shows what it breaks before anything is deployed.

### Roles
`owner`, `expert`. Fixture actors: owner = ana; expert = eli. The kernel appears as the actor `external:kernel` on record_* actions.

### Objects

**Source** — Where raw material lives: code, records, transcripts or the interview log.
| property | type | optional |
|---|---|---|
| kind | enum: repository, records, transcripts, interview-log | no |
| path | string | no |
| local_only | boolean | yes |
| sha256 | string | yes |
| stage | enum: added, fetched | no |

**Question** — A question in a stage's bundle, for the owner to answer.
| property | type | optional |
|---|---|---|
| stage | string | no |
| text | string | no |

**Answer** — The owner's answer, in their words; its decisions become proposed elements.
| property | type | optional |
|---|---|---|
| words | string | no |
| decisions | string | no |
| ref | string | yes |
| stage | enum: recorded | no |

**Element** — One part of the draft declaration (an object, action, cell, invariant...), proposed by an agent or confirmed by a person.
| property | type | optional |
|---|---|---|
| path | string | no |
| review | enum: proposed, confirmed, unknown | no |
| value | string | yes |
| cites | string | no |
| issues | integer | yes |
| issue_summary | string | yes |

**DecisionRequest** — A decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox.
| property | type | optional |
|---|---|---|
| subject | string | no |
| grounds | string | no |
| recommendation | string | no |
| stage | enum: open, decided | no |
| choice | string | yes |

**Commit** — An immutable snapshot of the working copy on a branch.
| property | type | optional |
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
| stage | enum: recorded | no |
| last_evidence | string | yes |
| evidence_error | string | yes |

**Draft** — The working copy of a domain's declaration on a branch: what a commit snapshots.
| property | type | optional |
|---|---|---|
| domain_id | string | no |
| declaration | string | no |
| branch | string | no |
| stage | enum: open | no |
| current_stage | string | yes |
| bundle | string | yes |
| merging | string | yes |
| conflicts | integer | yes |
| questions | string | yes |

### Links
| link | from | to | cardinality | required |
|---|---|---|---|---|
| question | Answer | Question | many-to-one | yes |
| element | DecisionRequest | Element | many-to-one | no |
| parents | Commit | Commit | many-to-many | no |
| origin | Element | Source | many-to-one | no |

### Actions

"Human only" = `requires: human`. "Records a decision" = `records_decision: true`.

| action | actor | target / creates | params | effects |
|---|---|---|---|---|
| add_source | owner | creates Source | kind (enum repository, records, transcripts, interview-log); path (string); local_only (boolean, optional) | none listed. Add a source of raw material: code, records, transcripts or the interview log. |
| fetch_source | owner | target Source | none | calls kernel service `fetch_source` with source = target.id; reply `record_fetch`. Fetch a link source into a snapshot, once. |
| record_fetch | external:kernel | target Source | sha256 (string) | sets target.sha256 = params.sha256. |
| ask_question | owner | creates Question | stage (string); text (string) | none listed. Ask a question of the current stage's bundle. |
| answer_question | owner, expert | creates Answer | question (ref Question); words (string); decisions (string) | calls kernel service `record_answer` with question = target.question.text, answer = target.words, decisions = target.decisions; reply `record_answer_ref`. |
| propose_element | owner | creates Element | path (string); origin (ref Source); cites (string); value (string) | calls kernel service `propose_element` with path = target.path, value = target.value, source = target.cites; reply `record_proposal`. |
| confirm_element | owner | target Element | none | Human only. Calls kernel service `confirm_element` with paths = target.path, approver = actor.id; reply `record_confirmation`. Only a person confirms. |
| mark_unknown | owner, expert | target Element | none | none listed. Mark an element as not known yet, instead of guessing. |
| request_decision | owner | creates DecisionRequest | element (ref Element); subject (string); grounds (string); recommendation (string) | none listed. Ask the owner for a decision only a person may take, with grounds and a recommendation. |
| decide | owner | target DecisionRequest | choice (string) | Human only; records a decision. Sets target.choice = params.choice. |
| commit_draft | owner | target Draft | none | calls kernel service `commit` with declaration = target.declaration; reply `record_commit`. Snapshot the working copy as an immutable commit. Cite its evidence on the commit with cite_evidence. |
| record_commit | external:kernel | creates Commit | seq (integer); content (string); interface (string); domain (string); branch (string); author (string) | sets target.domain_id = params.domain. |
| check_commit | owner | target Commit | none | calls kernel service `change_check` with domain = target.domain_id, commit = target.id; reply `record_check`. Precondition not-approved. |
| record_check | external:kernel | target Commit | passed (boolean); summary (string) | sets target.checks_passed = params.passed; target.failing = params.summary. Precondition settled. |
| approve_commit | owner | target Commit | none | Human only; records a decision. Calls kernel service `approve_commit` with domain = target.domain_id, commit = target.id, approver = actor.id; reply `record_approval`. Merges the commit into main and tags it. Only a person approves. Preconditions checks-pass, not-approved. |
| record_approval | external:kernel | target Commit | approved (boolean); main (string) | sets target.approved = params.approved; target.main = params.main. Record the approval and what main points to. Precondition approved-only-if-checked. |
| deliver | owner | target Commit | environment (enum: local) | none listed as effect; it is the trigger of the handoff (below). Ask Delivery to deliver an approved commit to an environment. Precondition approved. |
| record_proposal | external:kernel | target Element | issues (integer); summary (string) | sets target.issues = params.issues; target.issue_summary = params.summary. Record whether the drafted element was written into the working copy. |
| record_confirmation | external:kernel | target Element | confirmed (list of string) | none listed. Record that the working copy holds the element as confirmed. |
| record_answer_ref | external:kernel | target Answer | ref (string) | sets target.ref = params.ref. Record where the answer is in the interview log, so elements can cite it. |
| next_questions | owner | target Draft | none | calls kernel service `stage_questions` with no arguments; reply `record_questions`. Ask for the current stage's bundle of questions. |
| record_questions | external:kernel | target Draft | stage (string); bundle (string); questions (list of string); text (string) | sets target.current_stage = params.stage; target.bundle = params.bundle; target.questions = params.text. |
| search | owner | target Draft | query (string) | calls kernel service `search_sources` with query = params.query; reply `record_search`. Search the sources (redacted; local-only never served); the result is on record. |
| record_search | external:kernel | target Draft | refs (list of string) | none listed. Record which source chunks a search returned. |
| skip_stage | owner | target Draft | stage (string); reason (string) | Human only. Calls kernel service `skip_stage` with stage = params.stage, reason = params.reason; reply `record_skip`. Say an optional stage has nothing, in the owner's words. |
| record_skip | external:kernel | target Draft | skipped (boolean) | none listed. Record that the stage was skipped. |
| open_draft | owner | creates Draft | domain_id (string); declaration (string); branch (string) | none listed. Open a working copy of a domain's declaration on a branch, so it can be interviewed, committed and checked. |
| merge_main | owner | target Draft | none | calls kernel service `merge_main` with domain = target.domain_id, branch = target.branch, declaration = target.declaration; reply `record_merge`. Bring main into the branch's working copy and list the conflicts to resolve; the next commit records both parents. |
| checkout_commit | owner | target Draft | commit (string) | calls kernel service `checkout` with domain = target.domain_id, commit = params.commit, declaration = target.declaration; reply `record_checkout`. Load a commit into the working copy, to revert to it or build on it; committing it makes a new commit. |
| confirm_all_proposed | owner | target Draft | none | Human only. Calls kernel service `confirm_element` with paths = 'all' (the literal string `'all'`), approver = actor.id; reply `record_confirm_all`. Confirm every element still proposed in the working copy, as right. |
| record_merge | external:kernel | target Draft | merge (string); conflicts (integer); paths (list of string) | sets target.merging = params.merge; target.conflicts = params.conflicts. Record the merge in progress and how many conflicts it left. |
| record_checkout | external:kernel | target Draft | content (string) | none listed. Record that the working copy holds the commit's content. |
| record_confirm_all | external:kernel | target Draft | confirmed (list of string) | none listed. Record which elements were confirmed. |
| record_evidence | external:kernel | target Commit | strength (string); error (string) | sets target.last_evidence = params.strength; target.evidence_error = params.error. Record how strong the cited evidence is, or why it was refused. |
| cite_evidence | owner | target Commit | kind (enum: interview, source, check, event, approval-run); ref (string) | calls kernel service `cite_evidence` with domain = target.domain_id, commit = target.id, kind = params.kind, ref = params.ref; reply `record_evidence`. Cite evidence for a commit's change: an interview line, a source chunk, a check recorded on the commit, a stored event, or an approval run. The ref must resolve. Precondition not-approved. |

Actions only a person may take (`requires: human`): confirm_element, decide, approve_commit, skip_stage, confirm_all_proposed.
Actions that record a decision (`records_decision`): decide, approve_commit.

### Preconditions (Authoring)
| action | id | check | reason |
|---|---|---|---|
| check_commit | not-approved | target.approved != true | An approved commit passed its check; check a new commit instead. |
| record_check | settled | target.approved != true | An approved commit's check is settled; a late result is not recorded. |
| approve_commit | checks-pass | target.checks_passed == true | Run the change check, and approve only a commit that passes it. |
| approve_commit | not-approved | target.approved != true | Already approved; approve a newer commit. |
| record_approval | approved-only-if-checked | params.approved != true or target.checks_passed == true | A commit is recorded as approved only if its change check passed. |
| deliver | approved | target.approved == true | Only an approved commit is delivered. |
| cite_evidence | not-approved | target.approved != true | An approved commit is settled; cite evidence before approving it. |

### Transitions (Authoring)
Each table is keyed on the object's state field. A cell is a target state ("→ x"), a deny with its reason, or n/a.

**Source** (field stage, initial added)
| state | action | cell |
|---|---|---|
| added | fetch_source | → added |
| added | record_fetch | → fetched |
| fetched | fetch_source | deny: A link is fetched once into a snapshot; add a new source to read it again. |
| fetched | record_fetch | n/a |

**Element** (field review, initial proposed)
| state | action | cell |
|---|---|---|
| proposed | confirm_element | → confirmed |
| proposed | mark_unknown | → unknown |
| proposed | record_proposal | → proposed |
| proposed | record_confirmation | n/a |
| unknown | confirm_element | → confirmed |
| unknown | mark_unknown | n/a |
| unknown | record_proposal | n/a |
| unknown | record_confirmation | n/a |
| confirmed | confirm_element | n/a |
| confirmed | mark_unknown | deny: A confirmed element changes by a new proposal and a new commit, not by marking it unknown. |
| confirmed | record_proposal | n/a |
| confirmed | record_confirmation | → confirmed |

**DecisionRequest** (field stage, initial open)
| state | action | cell |
|---|---|---|
| open | decide | → decided |
| decided | decide | deny: Already decided; a new decision needs a new request. |

**Draft** (field stage, initial open). In state open, every one of these actions goes → open: commit_draft, next_questions, record_questions, search, record_search, skip_stage, record_skip, merge_main, record_merge, checkout_commit, record_checkout, confirm_all_proposed, record_confirm_all.

**Commit** (field stage, initial recorded). In state recorded, every one of these actions goes → recorded: check_commit, record_check, approve_commit, record_approval, deliver, record_evidence, cite_evidence.

**Answer** (field stage, initial recorded). In state recorded, record_answer_ref → recorded.

### Invariants (Authoring)
| id | on | check | reason |
|---|---|---|---|
| approved-commits-passed-their-checks | Commit | target.approved != true or target.checks_passed == true | An approved commit passed its change check. |
| decided-requests-record-the-choice | DecisionRequest | target.stage != 'decided' or exists(target.choice) | A decided request records what was chosen. |
| fetched-sources-have-a-snapshot | Source | target.stage != 'fetched' or exists(target.sha256) | A fetched source has the hash of its snapshot. |
| elements-cite-a-source | Element | exists(target.origin) | Every element cites where it came from. |

### Rules (Authoring): only a person
| rule id | on | requires | reason |
|---|---|---|---|
| only-a-person-commit-approved | Commit.approved | human | Only a person sets the approved of a Commit: every action that does so today requires a person (approve_commit). |
| only-a-person-commit-main | Commit.main | human | Only a person sets the main of a Commit: every action that does so today requires a person (approve_commit). |
| only-a-person-decisionrequest-choice | DecisionRequest.choice | human | Only a person sets the choice of a DecisionRequest: every action that does so today requires a person (decide). |
| only-a-person-decisionrequest-decided | DecisionRequest.decided | human | Only a person brings a DecisionRequest to decided: every action that does so today requires a person (decide). |
| only-a-person-element-confirmed | Element.confirmed | human | Only a person brings an Element to confirmed: every action that does so today requires a person (confirm_element). |

### Glossary (Authoring)
- **commit**: An immutable snapshot of the working copy. Every change is a new commit; nothing is edited in place.
- **main**: The protected branch. A commit reaches main only by being approved, and only commits on main are delivered.
- **approval**: A person's decision that merges a commit into main and tags it. It cannot be undone; a newer approved commit supersedes it.
- **element**: One part of a declaration (an object, a link, an action, a cell, an invariant), drafted by an agent and confirmed only by a person.
- **draft**: The working copy of a domain's declaration on a branch: what the next commit will snapshot.
- **change check**: The checks a commit runs before approval: structure, semantics, scenarios, harness, past actions, stranded objects.
- **unknown**: An element marked as not known yet, instead of guessed. It stays visible until someone answers it.

### World fixtures (Authoring)
Actors: owner ana; expert eli. Objects: Source S-code (repository, path src/toprope, stage added); Source S-docs (records, path docs, stage fetched, sha256 5f1c); Question Q1 (stage purpose, text "What problem does this domain solve, and for whom?"); Answer A1 (question Q1, words "Owners turn workflows into domains without code."); Element E1 (path purpose, origin S-docs, review proposed); E2 (path objects.Commit, origin S-code, review confirmed); E3 (path actions.mark_unknown, origin S-docs, review unknown); DecisionRequest DR1 (element E1, subject "Which success metric?", grounds "The scope document names two.", recommendation "Human minutes to a confirmed version.", stage open); Draft D1 (domain_id authoring, declaration domains/authoring/authoring.domain.yaml, branch work, stage open); Commit C1 (seq 1, content a1b2, branch work, interface 1.0.0, domain_id authoring, recorded, checks_passed true, approved true, main C1); C2 (seq 2, c3d4, work, 1.1.0, authoring, recorded, checks_passed false); C3 (seq 3, e5f6, work, 1.2.0, authoring, recorded, checks_passed true).

## Delivery

### Purpose
- Problem: An approved domain version must become working software in an environment, and nothing unverified may reach it.
- Success metric: "share of approved versions that reach verified-in-use without a manual fix or rollback"; direction: up.
- Announcement: Approved domain versions now reach the environment as working software in one step. Nothing that fails its checks or lacks a person's approval gets there.

### Roles
`approver` (fixture: ana). `request_delivery` is taken by actor `system`; record_* actions by `external:kernel`.

### Objects

**DeliveryRequest** — A request to deliver an approved commit of a domain, handed off by Authoring.
| property | type | optional |
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
| stage | enum: requested, previewing, previewed, deploying, done, verified | no |
| probes_passed | boolean | yes |
| probe_summary | string | yes |

**Environment** — Where a domain runs; it points at one deployed commit.
| property | type | optional |
|---|---|---|
| name | string | no |
| current_commit | string | yes |

### Links
None.

### Actions
| action | actor | target / creates | params | effects |
|---|---|---|---|---|
| request_delivery | system | creates DeliveryRequest | domain_id, commit, interface, environment, approver (all string) | none listed. Receive a request to deliver an approved commit, handed off by Authoring. |
| preview | approver | target DeliveryRequest | none | calls kernel service `preview` with domain = target.domain_id, commit = target.commit; reply `record_build`. Build the commit and run its harness, before anything is deployed. Precondition not-deployed. |
| record_build | external:kernel | target DeliveryRequest | build (string); harness_ok (boolean) | sets target.build = params.build; target.harness_ok = params.harness_ok. |
| deploy | approver | target DeliveryRequest | none | Human only; records a decision. Calls kernel service `deploy` with domain = target.domain_id, commit = target.commit, approver = actor.id; reply `record_deployment`. Deploy the commit, under the fixed floor. Only a person deploys. Precondition harness-passed. |
| record_deployment | external:kernel | target DeliveryRequest | deployed (boolean); error (string) | sets target.deployed = params.deployed; target.refusal = params.error; target.probes_passed = false. Record whether the deploy happened, or which floor rule refused it. A new deploy clears the earlier probes. |
| verify | approver | target DeliveryRequest | none | Human only. Sets target.verified = true. Verify the deployed domain in use, after its probes passed. Only a person verifies. Preconditions deployed, probes-passed. |
| record_probes | external:kernel | target DeliveryRequest | passed (boolean); summary (string) | sets target.probes_passed = params.passed; target.probe_summary = params.summary. Record what the probes found on the deployed commit. |
| run_probes | approver | target DeliveryRequest | none | calls kernel service `probe` with domain = target.domain_id, commit = target.commit; reply `record_probes`. Run the probes on the deployed commit: its build, its scenarios where it runs, and the objects in use against every invariant. Precondition deployed. |

Human only: deploy, verify. Records a decision: deploy.

### Preconditions (Delivery)
| action | id | check | reason |
|---|---|---|---|
| preview | not-deployed | target.deployed != true | Already deployed; deliver again with a new request. |
| deploy | harness-passed | target.harness_ok == true | Deploy only a build whose harness passed. |
| verify | deployed | target.deployed == true | Only a deployment that happened can be verified. |
| verify | probes-passed | target.probes_passed == true | Run the probes on the deployment first; verify only one whose probes passed. |
| run_probes | deployed | target.deployed == true | Only a deployment that happened can be probed. |

### Transitions (Delivery)
DeliveryRequest, field stage, initial requested.

| state | action | cell |
|---|---|---|
| requested | preview | → previewing |
| requested | record_build | n/a |
| requested | deploy | deny: Preview it first. |
| requested | record_deployment | n/a |
| requested | verify | n/a |
| requested | run_probes | n/a |
| requested | record_probes | n/a |
| previewing | preview | deny: A preview is running. |
| previewing | record_build | → previewed |
| previewing | deploy | deny: The preview has not finished. |
| previewing | record_deployment | n/a |
| previewing | verify | n/a |
| previewing | run_probes | n/a |
| previewing | record_probes | n/a |
| previewed | preview | → previewing |
| previewed | record_build | n/a |
| previewed | deploy | → deploying |
| previewed | record_deployment | n/a |
| previewed | verify | n/a |
| previewed | run_probes | n/a |
| previewed | record_probes | n/a |
| deploying | preview | deny: A deploy is running. |
| deploying | record_build | n/a |
| deploying | deploy | deny: A deploy is running. |
| deploying | record_deployment | → done |
| deploying | verify | n/a |
| deploying | run_probes | n/a |
| deploying | record_probes | n/a |
| done | preview | → previewing |
| done | record_build | n/a |
| done | deploy | → deploying |
| done | record_deployment | n/a |
| done | verify | → verified |
| done | run_probes | → done |
| done | record_probes | → done |
| verified | preview | n/a |
| verified | record_build | n/a |
| verified | deploy | n/a |
| verified | record_deployment | n/a |
| verified | verify | deny: Already verified. |
| verified | run_probes | n/a |
| verified | record_probes | n/a |

### Invariants (Delivery)
| id | on | check | reason |
|---|---|---|---|
| deployed-builds-passed-their-harness | DeliveryRequest | target.deployed != true or target.harness_ok == true | Nothing reaches the environment unless its harness passed. |
| verified-requests-were-deployed | DeliveryRequest | target.stage != 'verified' or target.deployed == true | Only a deployment that happened is verified. |
| finished-deploys-record-the-outcome | DeliveryRequest | target.stage not in ['done', 'verified'] or exists(target.deployed) | A finished deploy records whether it happened. |
| deploying-builds-passed-their-harness | DeliveryRequest | target.stage != 'deploying' or target.harness_ok == true | A deploy starts only from a build whose harness passed. |
| verified-requests-passed-their-probes | DeliveryRequest | target.stage != 'verified' or target.probes_passed == true | A verified deployment passed its probes. |

### Rules (Delivery): only a person
| rule id | on | requires | reason |
|---|---|---|---|
| only-a-person-deliveryrequest-deployed | DeliveryRequest.deployed | human | Only a person sets the deployed of a DeliveryRequest: every action that does so today requires a person (deploy). |
| only-a-person-deliveryrequest-deploying | DeliveryRequest.deploying | human | Only a person brings a DeliveryRequest to deploying: every action that does so today requires a person (deploy). |
| only-a-person-deliveryrequest-done | DeliveryRequest.done | human | Only a person brings a DeliveryRequest to done: every action that does so today requires a person (deploy). |
| only-a-person-deliveryrequest-refusal | DeliveryRequest.refusal | human | Only a person sets the refusal of a DeliveryRequest: every action that does so today requires a person (deploy). |
| only-a-person-deliveryrequest-verified | DeliveryRequest.verified | human | Only a person brings a DeliveryRequest to verified: every action that does so today requires a person (verify). |

### Glossary (Delivery)
- **delivery request**: A request, handed over from Authoring, to put one approved commit of a domain into an environment.
- **preview**: Building a commit and running its harness before anything is deployed; a preview changes no environment.
- **deploy floor**: Rules the kernel enforces on every deploy that no declaration can weaken: approved, on main, not a downgrade, harness passed, a person deploys, nothing stranded.
- **verified**: A deployment a person has verified in use, after its probes passed there.

### World fixtures (Delivery)
Actor: approver ana. Environment ENV-local (name local). DeliveryRequests, all with environment local and approver ana:
- R1: domain authoring, commit 2-c3d4, interface 1.1.0, stage requested.
- R2: authoring, 3-e5f6, 1.1.0, stage previewed, build b2, harness_ok false.
- R3: authoring, 4-a7b8, 1.2.0, stage done, build b3, harness_ok true, deployed false, refusal "stranded: E-live (state 'ended' is gone)".
- R4: delivery, 5-c9d0, 1.0.0, stage done, build b4, harness_ok true, deployed true, refusal "".
- R5: delivery, 6-e1f2, 1.0.0, stage done, build b5, harness_ok true, deployed true, refusal "", probes_passed true, probe_summary "passed: 4 of 4 scenario(s) pass; 1 object(s) checked".
- R6: authoring, 7-a3b4, 1.2.0, stage verified, build b6, harness_ok true, deployed true, refusal "", probes_passed true, probe_summary "passed: 9 of 9 scenario(s) pass; 3 object(s) checked", verified true.

## Handoff between the domains

Handoff `deliver_approved_commit` (declared in Authoring):
- Sent when: Authoring action `deliver` has outcome `ok`.
- To: domain `delivery`, interface `1.x`, action `request_delivery`.
- Parameters sent: domain_id = target.domain_id; commit = target.id; interface = target.interface; environment = params.environment; approver = actor.id.
- Handoff target: target.domain_id + ':' + target.id + ':' + params.environment.
- Wiring in the composition: `authoring.deliver_approved_commit` → `delivery.request_delivery`.
- What the receiver needs: `request_delivery` takes domain_id, commit, interface, environment and approver (all strings), and creates a DeliveryRequest with them. Delivery's `request_delivery` is taken by actor `system`.
