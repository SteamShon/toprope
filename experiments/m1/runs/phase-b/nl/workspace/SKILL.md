# SKILL: the Authoring and Delivery domains (composition toprope-self, version 1)

The composition `toprope-self` has two members: `authoring` (declaration authoring/authoring.domain.yaml, interface 1, domain version 9) and `delivery` (declaration delivery/delivery.domain.yaml, interface 1, domain version 1). One wire joins them: `authoring.deliver_approved_commit` to `delivery.request_delivery`.

## Authoring

**Purpose.** Problem: A domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code. Success metric: "human minutes from an owner's intent to a confirmed, compiled domain version", direction: down. Announcement: Domain owners now turn the workflow in their heads into a declared, checked domain without writing code. Every change shows what it breaks before anything is deployed.

**Roles.** owner, expert, agent, deputy. In the world, owner is ana and expert is eli; agent is an automated agent. A deputy is a person the owner names with name_deputy to approve commits while the owner is away. The kernel (`external:kernel`) is the actor of the record_* actions listed below.

### Authoring objects

Properties are required unless marked optional.

**Source** — Where raw material lives: code, records, transcripts or the interview log.
| Property | Type |
|---|---|
| kind | enum: repository, records, transcripts, interview-log |
| path | string |
| local_only | boolean |
| sha256 | string, optional |
| stage | enum: added, fetched (initial: added) |

**Question** — A question in a stage's bundle, for the owner to answer.
| Property | Type |
|---|---|
| stage | string |
| text | string |

**Answer** — The owner's answer, in their words; its decisions become proposed elements.
| Property | Type |
|---|---|
| words | string |
| decisions | string |
| ref | string, optional |
| stage | enum: recorded (initial: recorded) |

**Element** — One part of the draft declaration (an object, action, cell, invariant...), proposed by an agent or confirmed by a person.
| Property | Type |
|---|---|
| path | string |
| review | enum: proposed, confirmed, unknown, withdrawn (initial: proposed) |
| value | string, optional |
| cites | string |
| issues | integer, optional |
| issue_summary | string, optional |
| wording_only | boolean, optional (true when the element only fixes wording, not substance) |
| confirmation_reason | string, optional (why the owner agreed when confirming the element) |
| permission | boolean, optional (true when the element is about who may approve or deploy) |
| first_confirmer | string, optional (who confirmed the element first) |
| second_confirmer | string, optional (a different person who confirmed a permission element a second time) |
| drafted_by | string, optional (which agent drafted the element, so the owner can tell which agent drafted badly) |

**DecisionRequest** — A decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox.
| Property | Type |
|---|---|
| subject | string |
| grounds | string |
| recommendation | string |
| stage | enum: open, decided (initial: open) |
| choice | string, optional |
| deadline | string, optional (a date, YYYY-MM-DD) |

**Commit** — An immutable snapshot of the working copy on a branch.
| Property | Type |
|---|---|
| seq | integer |
| content | string |
| branch | string |
| author | string, optional |
| message | string, optional |
| interface | string |
| domain_id | string |
| checks_passed | boolean, optional |
| failing | string, optional |
| checked_at | string, optional (the time the change check was recorded) |
| approved | boolean, optional |
| wording_only | boolean, optional (true when the commit only changes wording, not substance) |
| main | string, optional |
| stage | enum: recorded (initial: recorded) |
| last_evidence | string, optional |
| evidence_error | string, optional |
| release_name | string, optional (the owner's name for the release, given to an approved commit) |

**Draft** — The working copy of a domain's declaration on a branch: what a commit snapshots.
| Property | Type |
|---|---|
| domain_id | string |
| declaration | string |
| branch | string |
| stage | enum: open (initial: open) |
| current_stage | string, optional |
| bundle | string, optional |
| merging | string, optional |
| conflicts | integer, optional |

**Deputy** — A person the owner has named to approve commits while the owner is away.
| Property | Type |
|---|---|
| person | string |
| until | string, optional (a date, YYYY-MM-DD, after which the deputy no longer approves) |
| stage | enum: active, ended (initial: active) |

### Authoring links

| Link | From | To | Cardinality | Required |
|---|---|---|---|---|
| question | Answer | Question | many-to-one | yes |
| element | DecisionRequest | Element | many-to-one | no |
| parents | Commit | Commit | many-to-many | no |
| origin | Element | Source | many-to-one | no |

### Authoring actions

Actors: owner, expert, agent, or `external:kernel`. A kernel service call names the service, its arguments, and the reply action that receives the result.

**add_source** — owner. Creates a Source. Params: kind (enum: repository, records, transcripts, interview-log); path (string); local_only (boolean, optional). Add a source of raw material: code, records, transcripts or the interview log.

**fetch_source** — owner. Target: Source. Fetch a link source into a snapshot, once. Effect: calls kernel service `fetch_source` with source = target.id; reply action `record_fetch`.

**record_fetch** — external:kernel. Target: Source. Param: sha256 (string). Records the fetched snapshot's hash. Effect: sets target.sha256 to params.sha256.

**ask_question** — owner or expert. Creates a Question. Params: stage (string); text (string). Ask a question of the current stage's bundle.

**answer_question** — owner or expert. Creates an Answer. Params: question (reference to a Question); words (string); decisions (string). Answer a question, in the person's own words. Effect: calls kernel service `record_answer` with question = target.question.text, answer = target.words, decisions = target.decisions; reply action `record_answer_ref`.

**propose_element** — owner. Creates an Element. Params: path (string); origin (reference to a Source); cites (string); value (string); wording_only (boolean, optional); drafted_by (string, optional, the agent that drafted the element). Propose a draft element that cites where it came from, and record which agent drafted it. Effect: sets target.drafted_by to params.drafted_by; calls kernel service `propose_element` with path = target.path, value = target.value, source = target.cites; reply action `record_proposal`.

**confirm_element** — owner. Target: Element. `requires: human` (only a person may take it). Param: reason (string), why the owner agreed. Confirm a drafted element. Only a person confirms. The reason is kept on the element as a note. An element about who may approve or deploy (permission true) is not settled by this confirmation alone: a second person must confirm it with second_confirm_element. Effect: sets target.confirmation_reason to params.reason and target.first_confirmer to actor.id; calls kernel service `confirm_element` with paths = target.path, approver = actor.id; reply action `record_confirmation`.

**confirm_wording_element** — agent. Target: Element. Confirm a drafted element that only fixes wording. An agent may confirm only an element marked wording_only; any other element is confirmed by a person with confirm_element. Effect: calls kernel service `confirm_element` with paths = target.path, approver = actor.id; reply action `record_confirmation`.
Preconditions:
| id | check | reason |
|---|---|---|
| wording-only | target.wording_only == true | An agent confirms only an element that only fixes wording; substance is confirmed by a person. |

**second_confirm_element** — owner or expert. Target: Element. `requires: human` (only a person may take it). Param: reason (string), why this second person agreed. A second, different person confirms an element about who may approve or deploy, after the first confirmation. Effect: sets target.second_confirmer to actor.id.
Preconditions:
| id | check | reason |
|---|---|---|
| permission-element | target.permission == true | Only an element about who may approve or deploy needs a second confirmation. |
| first-confirmed | target.review == 'confirmed' | The element must be confirmed by a first person before a second confirms it. |
| different-person | target.first_confirmer != actor.id | The second confirmation must come from a different person than the first. |

**mark_unknown** — owner or expert. Target: Element. Mark an element as not known yet, instead of guessing.

**withdraw_element** — owner. Target: Element. Withdraw a proposed element that is simply wrong, so it leaves the draft instead of staying as noise marked unknown. Only a proposed element can be withdrawn.

**request_decision** — owner. Creates a DecisionRequest. Params: element (reference to an Element); subject (string); grounds (string); recommendation (string); deadline (string, optional, a date YYYY-MM-DD). Ask the owner for a decision only a person may take, with grounds and a recommendation. If a deadline is given, it is stored on the request and shown to the owner with the request when it is asked.

**decide** — owner. Target: DecisionRequest. Param: choice (string). `requires: human`; records a decision. Decide a requested decision. Effect: sets target.choice to params.choice.

**decide_from_chat** — agent. Target: DecisionRequest. Params: choice (string); owner_words (string, the owner's words in chat that settle the request). Settle a decision request when the owner has said the choice in chat, so the owner is not asked again on the terminal. The agent writes the owner's words down; it does not choose for the owner. Records a decision. Effect: sets target.choice to params.choice.
Preconditions:
| id | check | reason |
|---|---|---|
| owner-words-written | exists(params.owner_words) and params.owner_words != '' | An agent settles a request only when it quotes the owner's words in chat that give the choice. |

**commit_draft** — owner. Target: Draft. Snapshot the working copy as an immutable commit. Cite its evidence on the commit with cite_evidence. Effect: calls kernel service `commit` with declaration = target.declaration; reply action `record_commit`.

**record_commit** — external:kernel. Creates a Commit. Params: seq (integer); content (string); interface (string); domain (string); branch (string); author (string). Record the commit the kernel made. Effect: sets target.domain_id to params.domain.

**check_commit** — owner. Target: Commit. Run the change check on a commit. Effect: calls kernel service `change_check` with domain = target.domain_id, commit = target.id; reply action `record_check`.
Preconditions:
| id | check | reason |
|---|---|---|
| not-approved | target.approved != true | An approved commit passed its check; check a new commit instead. |

**record_check** — external:kernel. Target: Commit. Params: passed (boolean); summary (string). Record the change check's result on the commit. Effect: sets target.checks_passed to params.passed, target.failing to params.summary and target.checked_at to the time of recording.
Preconditions:
| id | check | reason |
|---|---|---|
| settled | target.approved != true | An approved commit's check is settled; a late result is not recorded. |

**name_deputy** — owner. Creates a Deputy. `requires: human`. Params: person (string); until (string, optional, a date YYYY-MM-DD). Name a deputy who may approve commits while the owner is away, so changes do not wait for one person.

**end_deputy** — owner. Target: Deputy. `requires: human`. End the deputy's right to approve commits.
Preconditions:
| id | check | reason |
|---|---|---|
| active | target.stage == 'active' | Only an active deputy can be ended. |

**approve_commit** — owner or deputy. Target: Commit. `requires: human`; records a decision. Approve a commit: merge it into main and tag it. Only a person approves; a deputy approves under the same preconditions as the owner, and only while named and not ended or past its until date. Effect: calls kernel service `approve_commit` with domain = target.domain_id, commit = target.id, approver = actor.id; reply action `record_approval`.
Preconditions:
| id | check | reason |
|---|---|---|
| checks-pass | (target.checks_passed == true and the check is less than one day old (now - target.checked_at < 1 day)) or target.wording_only == true | Run the change check, and approve only a commit that passes it; a check a day old or older no longer counts, so run it again. A commit that only changes wording may be approved without the check. |
| not-approved | target.approved != true | Already approved; approve a newer commit. |

**name_release** — owner. Target: Commit. Param: name (string). Give an approved commit a release name, so people can talk about the release instead of the commit id. Effect: sets target.release_name to params.name.
Preconditions:
| id | check | reason |
|---|---|---|
| approved | target.approved == true | Only an approved commit is given a release name. |
| name-written | exists(params.name) and params.name != '' | A release name must be written. |

**record_approval** — external:kernel. Target: Commit. Params: approved (boolean); main (string). Record the approval and what main points to. Effect: sets target.approved to params.approved and target.main to params.main.
Preconditions:
| id | check | reason |
|---|---|---|
| approved-only-if-checked | params.approved != true or (target.checks_passed == true and now - target.checked_at < 1 day) or target.wording_only == true | A commit is recorded as approved only if its change check passed less than a day ago, or it only changes wording. |

**deliver** — owner. Target: Commit. Param: environment (enum: local, staging). Ask Delivery to deliver an approved commit to an environment. It triggers the handoff described below.
Preconditions:
| id | check | reason |
|---|---|---|
| approved | target.approved == true | Only an approved commit is delivered. |

**record_proposal** — external:kernel. Target: Element. Params: issues (integer); summary (string). Record whether the drafted element was written into the working copy. Effect: sets target.issues to params.issues and target.issue_summary to params.summary.

**record_confirmation** — external:kernel. Target: Element. Param: confirmed (list of strings). Record that the working copy holds the element as confirmed. No property effect.

**record_answer_ref** — external:kernel. Target: Answer. Param: ref (string). Record where the answer is in the interview log, so elements can cite it. Effect: sets target.ref to params.ref.

**next_questions** — owner. Target: Draft. Ask for the current stage's bundle of questions. Effect: calls kernel service `stage_questions` with no arguments; reply action `record_questions`.

**record_questions** — external:kernel. Target: Draft. Params: stage (string); bundle (string); questions (list of strings). Record the current stage and its bundle. Effect: sets target.current_stage to params.stage and target.bundle to params.bundle.

**search** — owner. Target: Draft. Param: query (string). Search the sources (redacted; local-only never served); the result is on record. Effect: calls kernel service `search_sources` with query = params.query; reply action `record_search`.

**record_search** — external:kernel. Target: Draft. Param: refs (list of strings). Record which source chunks a search returned. No property effect.

**skip_stage** — owner. Target: Draft. `requires: human`. Params: stage (string); reason (string). Say a stage has nothing, in the owner's words. This works for an optional stage and also for a required one, provided the owner writes why in reason. Effect: calls kernel service `skip_stage` with stage = params.stage, reason = params.reason; reply action `record_skip`.
Preconditions:
| id | check | reason |
|---|---|---|
| reason-written | exists(params.reason) and params.reason != '' | A stage is skipped only when the owner writes why it has nothing to say. |

**record_skip** — external:kernel. Target: Draft. Param: skipped (boolean). Record that the stage was skipped. No property effect.

**open_draft** — owner. Creates a Draft. Params: domain_id (string); declaration (string); branch (string). Open a working copy of a domain's declaration on a branch, so it can be interviewed, committed and checked.

**merge_main** — owner. Target: Draft. Bring main into the branch's working copy and list the conflicts to resolve; the next commit records both parents. Effect: calls kernel service `merge_main` with domain = target.domain_id, branch = target.branch, declaration = target.declaration; reply action `record_merge`.

**record_merge** — external:kernel. Target: Draft. Params: merge (string); conflicts (integer); paths (list of strings). Record the merge in progress and how many conflicts it left. Effect: sets target.merging to params.merge and target.conflicts to params.conflicts.

**checkout_commit** — owner. Target: Draft. Param: commit (string). Load a commit into the working copy, to revert to it or build on it; committing it makes a new commit. Effect: calls kernel service `checkout` with domain = target.domain_id, commit = params.commit, declaration = target.declaration; reply action `record_checkout`.

**record_checkout** — external:kernel. Target: Draft. Param: content (string). Record that the working copy holds the commit's content. No property effect.

**confirm_all_proposed** — owner. Target: Draft. `requires: human`. Confirm every element still proposed in the working copy, as right. Effect: calls kernel service `confirm_element` with paths = 'all' (the literal string all), approver = actor.id; reply action `record_confirm_all`.

**record_confirm_all** — external:kernel. Target: Draft. Param: confirmed (list of strings). Record which elements were confirmed. No property effect.

**record_evidence** — external:kernel. Target: Commit. Params: strength (string); error (string). Record how strong the cited evidence is, or why it was refused. Effect: sets target.last_evidence to params.strength and target.evidence_error to params.error.

**cite_evidence** — owner. Target: Commit. Params: kind (enum: interview, source, check, event, approval-run); ref (string). Cite evidence for a commit's change: an interview line, a source chunk, a check recorded on the commit, a stored event, or an approval run. The ref must resolve. Effect: calls kernel service `cite_evidence` with domain = target.domain_id, commit = target.id, kind = params.kind, ref = params.ref; reply action `record_evidence`.
Preconditions:
| id | check | reason |
|---|---|---|
| not-approved | target.approved != true | An approved commit is settled; cite evidence before approving it. |

**Human-only actions (requires: human):** confirm_element, second_confirm_element, decide, approve_commit, skip_stage, confirm_all_proposed, name_deputy, end_deputy.
**Actions that record a decision:** decide, decide_from_chat, approve_commit.

### Authoring transitions

Each table gives the state field, the initial state, and, for each current state, the result of each action. "to X" means the field becomes X. "deny" means the action is refused with the quoted reason (a denial by a transition table, not a precondition). "n/a" is as written in the table.

**Source.stage** (initial: added)
| State | Action | Result |
|---|---|---|
| added | fetch_source | to added |
| added | record_fetch | to fetched |
| fetched | fetch_source | deny: "A link is fetched once into a snapshot; add a new source to read it again." |
| fetched | record_fetch | n/a |

**Element.review** (initial: proposed)
| State | Action | Result |
|---|---|---|
| proposed | confirm_element | to confirmed |
| proposed | confirm_wording_element | to confirmed |
| proposed | second_confirm_element | n/a |
| proposed | mark_unknown | to unknown |
| proposed | record_proposal | to proposed |
| proposed | record_confirmation | n/a |
| proposed | withdraw_element | to withdrawn |
| unknown | confirm_element | to confirmed |
| unknown | confirm_wording_element | to confirmed |
| unknown | second_confirm_element | n/a |
| unknown | mark_unknown | n/a |
| unknown | record_proposal | n/a |
| unknown | record_confirmation | n/a |
| unknown | withdraw_element | n/a |
| confirmed | confirm_element | n/a |
| confirmed | confirm_wording_element | n/a |
| confirmed | second_confirm_element | n/a |
| confirmed | mark_unknown | deny: "A confirmed element changes by a new proposal and a new commit, not by marking it unknown." |
| confirmed | record_proposal | n/a |
| confirmed | record_confirmation | to confirmed |
| confirmed | withdraw_element | deny: "A confirmed element changes by a new proposal and a new commit, not by withdrawing it." |
| withdrawn | confirm_element | n/a |
| withdrawn | confirm_wording_element | n/a |
| withdrawn | second_confirm_element | n/a |
| withdrawn | mark_unknown | n/a |
| withdrawn | record_proposal | n/a |
| withdrawn | record_confirmation | n/a |
| withdrawn | withdraw_element | n/a |

**DecisionRequest.stage** (initial: open)
| State | Action | Result |
|---|---|---|
| open | decide | to decided |
| open | decide_from_chat | to decided |
| decided | decide | deny: "Already decided; a new decision needs a new request." |
| decided | decide_from_chat | deny: "Already decided; a new decision needs a new request." |

**Draft.stage** (initial: open). In state open, each of these actions goes to open: commit_draft, next_questions, record_questions, search, record_search, skip_stage, record_skip, merge_main, record_merge, checkout_commit, record_checkout, confirm_all_proposed, record_confirm_all.

**Commit.stage** (initial: recorded). In state recorded, each of these actions goes to recorded: check_commit, record_check, approve_commit, record_approval, name_release, deliver, record_evidence, cite_evidence.

**Deputy.stage** (initial: active)
| State | Action | Result |
|---|---|---|
| active | end_deputy | to ended |
| ended | end_deputy | deny: "Already ended; name a new deputy instead." |

**Answer.stage** (initial: recorded). In state recorded, record_answer_ref goes to recorded.

### Authoring invariants

| id | on | check | reason |
|---|---|---|---|
| approved-commits-passed-their-checks | Commit | target.approved != true or target.checks_passed == true or target.wording_only == true | An approved commit passed its change check, unless it only changes wording. |
| decided-requests-record-the-choice | DecisionRequest | target.stage != 'decided' or exists(target.choice) | A decided request records what was chosen. |
| fetched-sources-have-a-snapshot | Source | target.stage != 'fetched' or exists(target.sha256) | A fetched source has the hash of its snapshot. |
| elements-cite-a-source | Element | exists(target.origin) | Every element cites where it came from. |

### Authoring glossary

- **commit**: An immutable snapshot of the working copy. Every change is a new commit; nothing is edited in place.
- **main**: The protected branch. A commit reaches main only by being approved, and only commits on main are delivered.
- **deputy**: A person the owner names to approve commits while the owner is away. A deputy has the owner's right to approve, nothing more, until ended or past the until date.
- **approval**: A person's decision (the owner's, or a named deputy's) that merges a commit into main and tags it. It cannot be undone; a newer approved commit supersedes it.
- **element**: One part of a declaration (an object, a link, an action, a cell, an invariant), drafted by an agent and confirmed by a person; an agent may confirm only an element that only fixes wording (wording_only). An element about who may approve or deploy (permission) also needs a second, different person to confirm it.
- **withdrawn**: A proposed element the owner took back because it was wrong; it leaves the draft rather than staying as unknown.
- **draft**: The working copy of a domain's declaration on a branch: what the next commit will snapshot.
- **change check**: (A passing check counts only while it is less than one day old.) The checks a commit runs before approval: structure, semantics, scenarios, harness, past actions, stranded objects. A commit marked wording_only (it only changes wording) may be approved by a person without it.
- **unknown**: An element marked as not known yet, instead of guessed. It stays visible until someone answers it.

## Delivery

**Purpose.** Problem: An approved domain version must become working software in an environment, and nothing unverified may reach it. Success metric: "share of approved versions that reach verified-in-use without a manual fix or rollback", direction: up. Announcement: Approved domain versions now reach the environment as working software in one step. Nothing that fails its checks or lacks a person's approval gets there.

**Roles.** approver (in the world: ana). `system` is the actor of request_delivery and auto_deploy; `external:kernel` is the actor of the record_* actions.

### Delivery objects

**DeliveryRequest** — A request to deliver an approved commit of a domain, handed off by Authoring.
| Property | Type |
|---|---|
| domain_id | string |
| commit | string |
| interface | string |
| environment | string |
| approver | string |
| branch | string (the branch the commit came from) |
| replaced_commit | string, optional (the commit the environment pointed at when the request was received, i.e. what this delivery replaces; unset when the environment had none) |
| build | string, optional |
| harness_ok | boolean, optional |
| deployed | boolean, optional |
| refusal | string, optional |
| verified | boolean, optional |
| dry_run | boolean, optional (the result of a dry-run verification recorded before any deploy) |
| stage | enum: requested, built, deploying, done, verified (initial: requested) |

**Environment** — Where a domain runs; it points at one deployed commit.
| Property | Type |
|---|---|
| name | string |
| current_commit | string, optional |

Delivery has no links.

### Delivery actions

**request_delivery** — system. Creates a DeliveryRequest. Params: domain_id, commit, interface, environment, approver, branch (all strings). Receive a request to deliver an approved commit, handed off by Authoring. The request must say which branch the commit came from. Effect: sets target.replaced_commit to the current_commit of the Environment named params.environment, if it has one, so the request shows what was running before; otherwise leaves it unset.
Preconditions:
| id | check | reason |
|---|---|---|
| branch-stated | exists(params.branch) and params.branch != '' | A delivery request must say which branch its commit came from. |

**preview** — approver. Target: DeliveryRequest. Build the commit and run its harness, before anything is deployed. Effect: calls kernel service `preview` with domain = target.domain_id, commit = target.commit; reply action `record_build`.

**record_build** — external:kernel. Target: DeliveryRequest. Params: build (string); harness_ok (boolean). Record the build and its harness result. Effect: sets target.build to params.build and target.harness_ok to params.harness_ok.

**deploy** — approver. Target: DeliveryRequest. `requires: human`; records a decision. Deploy the commit, under the fixed floor. Only a person deploys. Effect: calls kernel service `deploy` with domain = target.domain_id, commit = target.commit, approver = actor.id; reply action `record_deployment`.
Preconditions:
| id | check | reason |
|---|---|---|
| harness-passed | target.harness_ok == true | Deploy only a build whose harness passed. |

**auto_deploy** — system. Target: DeliveryRequest. Deploy on its own once the preview has passed, without waiting for a person to press deploy. It fires when record_build has recorded harness_ok true. Effect: calls kernel service `deploy` with domain = target.domain_id, commit = target.commit, approver = target.approver; reply action `record_deployment`.
Preconditions:
| id | check | reason |
|---|---|---|
| harness-passed | target.harness_ok == true | Deploy only a build whose harness passed. |
| built | target.stage == 'built' | Only a previewed (built) request is deployed. |

**record_deployment** — external:kernel. Target: DeliveryRequest. Params: deployed (boolean); error (string). Record whether the deploy happened, or which floor rule refused it. Effect: sets target.deployed to params.deployed and target.refusal to params.error.

**verify** — approver. Target: DeliveryRequest. `requires: human`. Param: verified (boolean). Confirm the deployed domain works in use (the probes). Once the build is built, a person may also verify before it is deployed, to record a dry run. Effect: if target.deployed == true, sets target.verified to params.verified; otherwise (a dry run) sets target.dry_run to params.verified, leaves verified unset and leaves the stage as built.
Preconditions:
| id | check | reason |
|---|---|---|
| deployed-or-dry-run | target.deployed == true or target.stage == 'built' | Only a deployment that happened can be verified; before a deploy, only a built request can record a dry run. |

Human-only actions: deploy, verify. Actions that record a decision: deploy.

### Delivery transitions

**DeliveryRequest.stage** (initial: requested)
| State | Action | Result |
|---|---|---|
| requested | preview | to built |
| requested | record_build | n/a |
| requested | auto_deploy | deny: "Preview it first." |
| requested | deploy | deny: "Preview it first." |
| requested | record_deployment | n/a |
| requested | verify | n/a |
| built | preview | to built |
| built | record_build | n/a |
| built | auto_deploy | to deploying |
| built | deploy | to deploying |
| built | record_deployment | n/a |
| built | verify | to built (a dry run; records dry_run, not verified) |
| deploying | preview | deny: "A deploy is running." |
| deploying | record_build | n/a |
| deploying | auto_deploy | deny: "A deploy is running." |
| deploying | deploy | deny: "A deploy is running." |
| deploying | record_deployment | to done |
| deploying | verify | n/a |
| done | preview | to built |
| done | record_build | n/a |
| done | auto_deploy | n/a |
| done | deploy | to deploying |
| done | record_deployment | n/a |
| done | verify | to verified |
| verified | preview | n/a |
| verified | record_build | n/a |
| verified | auto_deploy | n/a |
| verified | deploy | n/a |
| verified | record_deployment | n/a |
| verified | verify | deny: "Already verified." |

### Delivery invariants

| id | on | check | reason |
|---|---|---|---|
| deployed-builds-passed-their-harness | DeliveryRequest | target.deployed != true or target.harness_ok == true | Nothing reaches the environment unless its harness passed. |
| verified-requests-were-deployed | DeliveryRequest | target.stage != 'verified' or target.deployed == true | Only a deployment that happened is verified. |
| finished-deploys-record-the-outcome | DeliveryRequest | target.stage not in ['done', 'verified'] or exists(target.deployed) | A finished deploy records whether it happened. |
| deploying-builds-passed-their-harness | DeliveryRequest | target.stage != 'deploying' or target.harness_ok == true | A deploy starts only from a build whose harness passed. |

### Delivery glossary

- **delivery request**: A request, handed over from Authoring, to put one approved commit of a domain into an environment.
- **preview**: Building a commit and running its harness before anything is deployed; a preview changes no environment.
- **deploy floor**: Rules the kernel enforces on every deploy that no declaration can weaken: approved, on main, not a downgrade, harness passed, a person deploys, nothing stranded.
- **verified**: A deployment a person has checked in use, after it happened.
- **dry run**: A verification a person records on a built request before it is deployed, to rehearse; it sets dry_run, not verified, and does not count as a verified deployment.

## Handoff between the domains

Wiring in the composition: `authoring.deliver_approved_commit` goes to `delivery.request_delivery`.

Handoff `deliver_approved_commit`: it fires when the Authoring action `deliver` has outcome ok. It goes to domain delivery, interface 1.x, action `request_delivery`. What is sent:
| request_delivery param | Value from Authoring |
|---|---|
| domain_id | target.domain_id |
| commit | target.id |
| interface | target.interface |
| environment | params.environment |
| approver | actor.id |
| branch | target.branch |

The handoff target is target.domain_id + ':' + target.id + ':' + params.environment.

What the receiver needs: request_delivery takes domain_id, commit, interface, environment, approver and branch, all strings, and creates a DeliveryRequest (stage requested) that shows, in replaced_commit, the commit the environment pointed at (not sent by Authoring; Delivery reads it from its own Environment). A request with no branch is refused (precondition `branch-stated`).
