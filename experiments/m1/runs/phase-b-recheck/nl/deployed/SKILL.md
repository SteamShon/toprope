# SKILL: the Authoring and Delivery domains (composition toprope-self)

Composition `toprope-self`, version 1. Members: `authoring` (declaration authoring/authoring.domain.yaml, interface 1) and `delivery` (declaration delivery/delivery.domain.yaml, interface 1). Wiring: `authoring.deliver_approved_commit` → `delivery.request_delivery`. Authoring declaration version 12; Delivery declaration version 6.

## Authoring

### Purpose
- Problem: A domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code.
- Success metric: "human minutes from an owner's intent to a confirmed, compiled domain version"; direction: down.
- Announcement: Domain owners now turn the workflow in their heads into a declared, checked domain without writing code. Every change shows what it breaks before anything is deployed.

### Roles
`owner`, `expert`, `agent`, `deputy`. Fixture actors: owner = ana; expert = eli. The `agent` role is an automated agent; it may confirm only elements that fix wording (confirm_wording_element). The `deputy` role is a person the owner has named (name_deputy) who may approve commits (approve_commit) while the owner is away; a deputy must be a person, never an agent, and has no other owner powers. The kernel appears as the actor `external:kernel` on record_* actions.

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
| review | enum: proposed, confirmed, unknown, withdrawn | no |
| value | string | yes |
| cites | string | no |
| issues | integer | yes |
| issue_summary | string | yes |
| wording_only | boolean | yes |
| confirm_reason | string | yes |
| drafted_by | string | yes |

**DecisionRequest** — A decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox.
| property | type | optional |
|---|---|---|
| subject | string | no |
| grounds | string | no |
| recommendation | string | no |
| stage | enum: open, decided | no |
| choice | string | yes |
| deadline | string | yes |
| owner_words | string | yes |

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
| checked_at | string | yes |
| failing | string | yes |
| approved | boolean | yes |
| wording_only | boolean | yes |
| main | string | yes |
| stage | enum: recorded | no |
| last_evidence | string | yes |
| evidence_error | string | yes |
| release_name | string | yes |

**Deputy** — A person the owner has named to approve commits while the owner is away.
| property | type | optional |
|---|---|---|
| person | string | no |
| away | boolean | yes |
| stage | enum: named | no |

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
| ask_question | owner, expert | creates Question | stage (string); text (string) | none listed. Ask a question of the current stage's bundle. |
| answer_question | owner, expert | creates Answer | question (ref Question); words (string); decisions (string) | calls kernel service `record_answer` with question = target.question.text, answer = target.words, decisions = target.decisions; reply `record_answer_ref`. |
| propose_element | owner | creates Element | path (string); origin (ref Source); cites (string); value (string); wording_only (boolean, optional); drafted_by (string, optional) | sets target.wording_only = params.wording_only; target.drafted_by = params.drafted_by. Name the agent that drafted the element in drafted_by, so the owner can tell which agent drafted a poor element; it is kept on the element. Calls kernel service `propose_element` with path = target.path, value = target.value, source = target.cites; reply `record_proposal`. Set wording_only only when the element changes wording and nothing of substance. |
| confirm_element | owner | target Element | reason (string) | Human only. Sets target.confirm_reason = params.reason. Calls kernel service `confirm_element` with paths = target.path, approver = actor.id; reply `record_confirmation`. Only a person confirms. The reason is a note on why the owner agreed, kept on the element for later readers. An element about who may approve or deploy (for example approval, deployment, or the only-a-person rules) needs a second person to confirm it as well: ask a different person than the first to confirm it, and treat it as confirmed only when both have. |
| confirm_wording_element | agent | target Element | reason (string) | Sets target.confirm_reason = params.reason. Calls kernel service `confirm_element` with paths = target.path, approver = actor.id; reply `record_confirmation`. An agent confirms an element that only fixes wording. The reason is a note on why it was accepted, kept on the element. Precondition wording-only. |
| mark_unknown | owner, expert | target Element | none | none listed. Mark an element as not known yet, instead of guessing. |
| withdraw_element | owner | target Element | none | none listed. Withdraw a proposed element that is simply wrong, so it leaves the draft instead of staying as an unknown. Only a proposed element can be withdrawn. |
| request_decision | owner | creates DecisionRequest | element (ref Element); subject (string); grounds (string); recommendation (string); deadline (string, optional) | sets target.deadline = params.deadline. Ask the owner for a decision only a person may take, with grounds and a recommendation. If a deadline (a date) is given, it is shown to the owner with the request when it is asked. |
| decide | owner | target DecisionRequest | choice (string) | Human only; records a decision. Sets target.choice = params.choice. |
| decide_from_chat | agent | target DecisionRequest | choice (string); owner_words (string) | Records a decision. Sets target.choice = params.choice; target.owner_words = params.owner_words. An agent settles a decision request when the owner has said the choice in chat; owner_words quotes the owner's words, kept on the request so later readers see the owner said it. Precondition owner-said-so. |
| commit_draft | owner | target Draft | none | calls kernel service `commit` with declaration = target.declaration; reply `record_commit`. Snapshot the working copy as an immutable commit. Cite its evidence on the commit with cite_evidence. |
| record_commit | external:kernel | creates Commit | seq (integer); content (string); interface (string); domain (string); branch (string); author (string) | sets target.domain_id = params.domain. |
| check_commit | owner | target Commit | none | calls kernel service `change_check` with domain = target.domain_id, commit = target.id; reply `record_check`. Precondition not-approved. |
| record_check | external:kernel | target Commit | passed (boolean); summary (string); checked_at (string, timestamp of the check run) | sets target.checks_passed = params.passed; target.checked_at = params.checked_at; target.failing = params.summary. Precondition settled. |
| name_deputy | owner | creates Deputy | person (string) | Human only. Name a person who may approve commits while the owner is away. The deputy is recorded with away unset. |
| set_away | owner | target Deputy | away (boolean) | Human only. Sets target.away = params.away. The owner says whether they are away; a deputy approves only while away is true. |
| approve_commit | owner, deputy | target Commit | wording_only (boolean, optional) | Human only; records a decision. Sets target.wording_only = params.wording_only. Calls kernel service `approve_commit` with domain = target.domain_id, commit = target.id, approver = actor.id; reply `record_approval`. Merges the commit into main and tags it. Only a person approves; the owner, or the named deputy while the owner is away (the approver is recorded). The deputy is bound by the same preconditions as the owner. Set wording_only only when the commit changes wording and nothing of substance; such a commit may be approved without a change check. Preconditions checks-pass, not-approved. |
| record_approval | external:kernel | target Commit | approved (boolean); main (string) | sets target.approved = params.approved; target.main = params.main. Record the approval and what main points to. Precondition approved-only-if-checked. |
| deliver | owner | target Commit | environment (enum: local, staging) | none listed as effect; it is the trigger of the handoff (below). Ask Delivery to deliver an approved commit to an environment. Precondition approved. |
| name_release | owner | target Commit | release_name (string) | Sets target.release_name = params.release_name. Give an approved commit a release name, so people can talk about releases instead of commit ids. Precondition approved. |
| record_proposal | external:kernel | target Element | issues (integer); summary (string) | sets target.issues = params.issues; target.issue_summary = params.summary. Record whether the drafted element was written into the working copy. |
| record_confirmation | external:kernel | target Element | confirmed (list of string) | none listed. Record that the working copy holds the element as confirmed. |
| record_answer_ref | external:kernel | target Answer | ref (string) | sets target.ref = params.ref. Record where the answer is in the interview log, so elements can cite it. |
| next_questions | owner | target Draft | none | calls kernel service `stage_questions` with no arguments; reply `record_questions`. Ask for the current stage's bundle of questions. |
| record_questions | external:kernel | target Draft | stage (string); bundle (string); questions (list of string); text (string) | sets target.current_stage = params.stage; target.bundle = params.bundle; target.questions = params.text. |
| search | owner | target Draft | query (string) | calls kernel service `search_sources` with query = params.query; reply `record_search`. Search the sources (redacted; local-only never served); the result is on record. |
| record_search | external:kernel | target Draft | refs (list of string) | none listed. Record which source chunks a search returned. |
| skip_stage | owner | target Draft | stage (string); reason (string) | Human only. Calls kernel service `skip_stage` with stage = params.stage, reason = params.reason; reply `record_skip`. Say a stage has nothing, in the owner's words. The stage may be optional or required; a required stage may be skipped only when the owner writes a reason (a non-empty reason is needed), since some domains have nothing to say at a stage the tool calls required. |
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

Actions only a person may take (`requires: human`): confirm_element, decide, approve_commit, skip_stage, confirm_all_proposed, name_deputy, set_away.
Actions that record a decision (`records_decision`): decide, decide_from_chat, approve_commit.

### Preconditions (Authoring)
| action | id | check | reason |
|---|---|---|---|
| check_commit | not-approved | target.approved != true | An approved commit passed its check; check a new commit instead. |
| record_check | settled | target.approved != true | An approved commit's check is settled; a late result is not recorded. |
| approve_commit | checks-pass | (target.checks_passed == true and exists(target.checked_at) and now - target.checked_at < 1 day) or params.wording_only == true | Run the change check, and approve only a commit that passes it with a check less than a day old, unless the commit changes wording only. A check run long ago may no longer reflect the toolchain; check again. |
| approve_commit | not-approved | target.approved != true | Already approved; approve a newer commit. |
| record_approval | approved-only-if-checked | params.approved != true or (target.checks_passed == true and exists(target.checked_at) and now - target.checked_at < 1 day) or target.wording_only == true | A commit is recorded as approved only if its change check passed less than a day ago, or it changes wording only. |
| deliver | approved | target.approved == true | Only an approved commit is delivered. |
| name_release | approved | target.approved == true | Only an approved commit is given a release name. |
| cite_evidence | not-approved | target.approved != true | An approved commit is settled; cite evidence before approving it. |
| decide_from_chat | owner-said-so | exists(params.owner_words) | An agent settles a decision request only when the owner's own words in chat give the choice; quote them. |
| confirm_wording_element | wording-only | target.wording_only == true | An agent confirms only an element that fixes wording; a person confirms the rest. |

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
| proposed | confirm_wording_element | → confirmed |
| proposed | mark_unknown | → unknown |
| proposed | withdraw_element | → withdrawn |
| proposed | record_proposal | → proposed |
| proposed | record_confirmation | n/a |
| unknown | confirm_element | → confirmed |
| unknown | confirm_wording_element | → confirmed |
| unknown | mark_unknown | n/a |
| unknown | withdraw_element | n/a |
| unknown | record_proposal | n/a |
| unknown | record_confirmation | n/a |
| confirmed | confirm_element | n/a |
| confirmed | confirm_wording_element | n/a |
| confirmed | mark_unknown | deny: A confirmed element changes by a new proposal and a new commit, not by marking it unknown. |
| confirmed | withdraw_element | deny: A confirmed element changes by a new proposal and a new commit, not by withdrawing it. |
| confirmed | record_proposal | n/a |
| confirmed | record_confirmation | → confirmed |
| withdrawn | confirm_element | n/a |
| withdrawn | confirm_wording_element | n/a |
| withdrawn | mark_unknown | n/a |
| withdrawn | withdraw_element | n/a |
| withdrawn | record_proposal | n/a |
| withdrawn | record_confirmation | n/a |

**DecisionRequest** (field stage, initial open)
| state | action | cell |
|---|---|---|
| open | decide | → decided |
| open | decide_from_chat | → decided |
| decided | decide | deny: Already decided; a new decision needs a new request. |
| decided | decide_from_chat | deny: Already decided; a new decision needs a new request. |

**Draft** (field stage, initial open). In state open, every one of these actions goes → open: commit_draft, next_questions, record_questions, search, record_search, skip_stage, record_skip, merge_main, record_merge, checkout_commit, record_checkout, confirm_all_proposed, record_confirm_all.

**Commit** (field stage, initial recorded). In state recorded, every one of these actions goes → recorded: check_commit, record_check, approve_commit, record_approval, deliver, name_release, record_evidence, cite_evidence.

**Answer** (field stage, initial recorded). In state recorded, record_answer_ref → recorded.

### Invariants (Authoring)
| id | on | check | reason |
|---|---|---|---|
| approved-commits-passed-their-checks | Commit | target.approved != true or target.checks_passed == true or target.wording_only == true | An approved commit passed its change check, unless it changes wording only. |
| decided-requests-record-the-choice | DecisionRequest | target.stage != 'decided' or exists(target.choice) | A decided request records what was chosen. |
| fetched-sources-have-a-snapshot | Source | target.stage != 'fetched' or exists(target.sha256) | A fetched source has the hash of its snapshot. |
| elements-cite-a-source | Element | exists(target.origin) | Every element cites where it came from. |

### Rules (Authoring): only a person
| rule id | on | requires | reason |
|---|---|---|---|
| only-a-person-commit-approved | Commit.approved | human | Only a person sets the approved of a Commit: every action that does so today requires a person (approve_commit). |
| only-a-person-commit-main | Commit.main | human | Only a person sets the main of a Commit: every action that does so today requires a person (approve_commit). |
| only-a-person-decisionrequest-choice | DecisionRequest.choice | human | Only a person sets the choice of a DecisionRequest (decide), except that an agent may record a choice the owner gave in chat (decide_from_chat). |
| only-a-person-decisionrequest-decided | DecisionRequest.decided | human | Only a person brings a DecisionRequest to decided (decide), except that an agent may do so when the owner said the choice in chat (decide_from_chat). |
| only-a-person-element-confirmed | Element.confirmed | human | Only a person brings an Element to confirmed, except that an agent may confirm an element marked wording_only (confirm_wording_element). |

### Glossary (Authoring)
- **commit**: An immutable snapshot of the working copy. Every change is a new commit; nothing is edited in place.
- **main**: The protected branch. A commit reaches main only by being approved, and only commits on main are delivered.
- **approval**: A person's decision that merges a commit into main and tags it. It cannot be undone; a newer approved commit supersedes it. The owner approves, or a named deputy while the owner is away.
- **deputy**: A person the owner names to approve commits while the owner is away, so changes do not wait for one person's absence. The deputy approves under the same checks as the owner.
- **element**: One part of a declaration (an object, a link, an action, a cell, an invariant), drafted by an agent and confirmed by a person; an agent may confirm an element that only fixes wording. An element about who may approve or deploy needs a second person's confirmation too, since permission rules matter most.
- **decision from chat**: When the owner states the choice for a decision request in chat, an agent may settle the request with that choice (decide_from_chat), quoting the owner's words; the owner need not answer again on the terminal.
- **draft**: The working copy of a domain's declaration on a branch: what the next commit will snapshot.
- **change check**: The checks a commit runs before approval: structure, semantics, scenarios, harness, past actions, stranded objects. A commit counts as checked only if its check passed less than a day ago (checked_at); an older check must be run again. A commit that changes wording only (wording_only) may be approved by a person without it.
- **withdrawn**: A proposed element the owner took back because it was wrong. It leaves the draft rather than lingering as unknown.
- **unknown**: An element marked as not known yet, instead of guessed. It stays visible until someone answers it.

### World fixtures (Authoring)
Actors: owner ana; expert eli. Objects: Source S-code (repository, path src/toprope, stage added); Source S-docs (records, path docs, stage fetched, sha256 5f1c); Question Q1 (stage purpose, text "What problem does this domain solve, and for whom?"); Answer A1 (question Q1, words "Owners turn workflows into domains without code."); Element E1 (path purpose, origin S-docs, review proposed); E2 (path objects.Commit, origin S-code, review confirmed); E3 (path actions.mark_unknown, origin S-docs, review unknown); DecisionRequest DR1 (element E1, subject "Which success metric?", grounds "The scope document names two.", recommendation "Human minutes to a confirmed version.", stage open); Draft D1 (domain_id authoring, declaration domains/authoring/authoring.domain.yaml, branch work, stage open); Commit C1 (seq 1, content a1b2, branch work, interface 1.0.0, domain_id authoring, recorded, checks_passed true, approved true, main C1); C2 (seq 2, c3d4, work, 1.1.0, authoring, recorded, checks_passed false); C3 (seq 3, e5f6, work, 1.2.0, authoring, recorded, checks_passed true).

## Delivery

### Purpose
- Problem: An approved domain version must become working software in an environment, and nothing unverified may reach it.
- Success metric: "share of approved versions that reach verified-in-use without a manual fix or rollback"; direction: up.
- Announcement: Approved domain versions now reach the environment as working software in one step. Nothing that fails its checks or lacks a person's approval gets there.

### Roles
`approver` (fixture: ana). `request_delivery` is taken by actor `system`, and so is `deploy` when it follows a passing preview; record_* actions by `external:kernel`.

### Objects

**DeliveryRequest** — A request to deliver an approved commit of a domain, handed off by Authoring.
| property | type | optional |
|---|---|---|
| domain_id | string | no |
| commit | string | no |
| interface | string | no |
| environment | string | no |
| approver | string | no |
| branch | string | no |
| build | string | yes |
| harness_ok | boolean | yes |
| deployed | boolean | yes |
| refusal | string | yes |
| verified | boolean | yes |
| stage | enum: requested, built, deploying, done, verified | no |
| probes_passed | boolean | yes |
| probe_summary | string | yes |
| dry_run | boolean | yes |
| replaced_commit | string | yes |

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
| request_delivery | system | creates DeliveryRequest | domain_id, commit, interface, environment, approver, branch (all string) | none listed. Receive a request to deliver an approved commit, handed off by Authoring. The request records the branch the commit came from. Precondition branch-stated. |
| preview | approver | target DeliveryRequest | none | calls kernel service `preview` with domain = target.domain_id, commit = target.commit; reply `record_build`. Build the commit and run its harness, before anything is deployed. Precondition not-deployed. |
| record_build | external:kernel | target DeliveryRequest | build (string); harness_ok (boolean) | sets target.build = params.build; target.harness_ok = params.harness_ok. |
| deploy | approver, system | target DeliveryRequest | none | Records a decision. Calls kernel service `deploy` with domain = target.domain_id, commit = target.commit, approver = target.approver when the actor is `system`, otherwise actor.id; reply `record_deployment`. Deploy the commit, under the fixed floor. The system takes this action on its own once a preview has recorded a passing harness (record_build with harness_ok = true), without waiting for a person; an approver may still take it. Precondition harness-passed. |
| record_deployment | external:kernel | target DeliveryRequest | deployed (boolean); error (string); replaced (string, optional) | sets target.deployed = params.deployed; target.refusal = params.error; target.probes_passed = false; target.replaced_commit = params.replaced. Record whether the deploy happened, or which floor rule refused it, and which commit the environment was running before (replaced; empty when nothing was running), so the request shows what it replaced. A new deploy clears the earlier probes. |
| verify | approver | target DeliveryRequest | dry_run (boolean, optional) | Human only. Sets target.dry_run = params.dry_run. Unless dry_run is true, sets target.verified = true: verify the deployed domain in use, after its probes passed. With dry_run = true, a delivery may be verified before it is deployed, to record a rehearsal: it records target.dry_run = true, does not set verified, and does not change the stage. Only a person verifies. Preconditions deployed, probes-passed (both waived by dry_run). |
| record_probes | external:kernel | target DeliveryRequest | passed (boolean); summary (string) | sets target.probes_passed = params.passed; target.probe_summary = params.summary. Record what the probes found on the deployed commit. |
| run_probes | approver | target DeliveryRequest | none | calls kernel service `probe` with domain = target.domain_id, commit = target.commit; reply `record_probes`. Run the probes on the deployed commit: its build, its scenarios where it runs, and the objects in use against every invariant. Precondition deployed. |

Human only: verify. Records a decision: deploy.

### Preconditions (Delivery)
| action | id | check | reason |
|---|---|---|---|
| request_delivery | branch-stated | exists(params.branch) | A delivery request must say which branch the commit came from. |
| preview | not-deployed | target.deployed != true | Already deployed; deliver again with a new request. |
| deploy | harness-passed | target.harness_ok == true | Deploy only a build whose harness passed. |
| verify | deployed | target.deployed == true or params.dry_run == true | Only a deployment that happened can be verified, unless this is a dry run. |
| verify | probes-passed | target.probes_passed == true or params.dry_run == true | Run the probes on the deployment first; verify only one whose probes passed, unless this is a dry run. |
| run_probes | deployed | target.deployed == true | Only a deployment that happened can be probed. |

### Transitions (Delivery)
DeliveryRequest, field stage, initial requested.

| state | action | cell |
|---|---|---|
| requested | preview | → built |
| requested | record_build | n/a |
| requested | deploy | deny: Preview it first. |
| requested | record_deployment | n/a |
| requested | verify | → requested (dry run only; otherwise denied by the preconditions) |
| requested | run_probes | n/a |
| requested | record_probes | n/a |
| built | preview | → built |
| built | record_build | → built |
| built | deploy | → deploying |
| built | record_deployment | n/a |
| built | verify | → built (dry run only; otherwise denied by the preconditions) |
| built | run_probes | n/a |
| built | record_probes | n/a |
| deploying | preview | deny: A deploy is running. |
| deploying | record_build | n/a |
| deploying | deploy | deny: A deploy is running. |
| deploying | record_deployment | → done |
| deploying | verify | n/a |
| deploying | run_probes | n/a |
| deploying | record_probes | n/a |
| done | preview | → built |
| done | record_build | n/a |
| done | deploy | → deploying |
| done | record_deployment | n/a |
| done | verify | → verified (with dry_run = true: → done) |
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
| only-a-person-deliveryrequest-verified | DeliveryRequest.verified | human | Only a person brings a DeliveryRequest to verified: every action that does so today requires a person (verify). |

### Glossary (Delivery)
- **delivery request**: A request, handed over from Authoring, to put one approved commit of a domain into an environment. It states the branch the commit came from, and is refused without it.
- **preview**: Building a commit and running its harness before anything is deployed; a preview changes no environment.
- **deploy floor**: Rules the kernel enforces on every deploy that no declaration can weaken: approved, on main, not a downgrade, harness passed, nothing stranded. A deploy follows a passing preview on its own; no one has to press deploy.
- **verified**: A deployment a person has verified in use, after its probes passed there.
- **replaced commit**: The commit the environment was running before this delivery was deployed, shown on the delivery request (replaced_commit) so the deployer sees what was running before. It is recorded when the deploy outcome is recorded.
- **dry run**: A verification a person records before the delivery is deployed, to rehearse. It is noted on the request (dry_run) but never makes it verified.

### World fixtures (Delivery)
Actor: approver ana. Environment ENV-local (name local). DeliveryRequests, all with environment local, approver ana and branch main:
- R1: domain authoring, commit 2-c3d4, interface 1.1.0, stage requested.
- R2: authoring, 3-e5f6, 1.1.0, stage built, build b2, harness_ok false.
- R3: authoring, 4-a7b8, 1.2.0, stage done, build b3, harness_ok true, deployed false, refusal "stranded: E-live (state 'ended' is gone)".
- R4: delivery, 5-c9d0, 1.0.0, stage done, build b4, harness_ok true, deployed true, refusal "".
- R5: delivery, 6-e1f2, 1.0.0, stage done, build b5, harness_ok true, deployed true, refusal "", probes_passed true, probe_summary "passed: 4 of 4 scenario(s) pass; 1 object(s) checked".
- R6: authoring, 7-a3b4, 1.2.0, stage verified, build b6, harness_ok true, deployed true, refusal "", probes_passed true, probe_summary "passed: 9 of 9 scenario(s) pass; 3 object(s) checked", verified true.

## Handoff between the domains

Handoff `deliver_approved_commit` (declared in Authoring):
- Sent when: Authoring action `deliver` has outcome `ok`.
- To: domain `delivery`, interface `1.x`, action `request_delivery`.
- Parameters sent: domain_id = target.domain_id; commit = target.id; interface = target.interface; environment = params.environment; approver = actor.id; branch = target.branch.
- Handoff target: target.domain_id + ':' + target.id + ':' + params.environment.
- Wiring in the composition: `authoring.deliver_approved_commit` → `delivery.request_delivery`.
- What the receiver needs: `request_delivery` takes domain_id, commit, interface, environment, approver and branch (all strings), and creates a DeliveryRequest with them; it refuses a request that does not state the branch. Delivery's `request_delivery` is taken by actor `system`.
