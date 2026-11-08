# SKILL: the Authoring and Delivery domains (composition toprope-self, version 1)

The composition `toprope-self` has two members: `authoring` (declaration authoring/authoring.domain.yaml, interface 1, domain version 9) and `delivery` (declaration delivery/delivery.domain.yaml, interface 1, domain version 1). One wire joins them: `authoring.deliver_approved_commit` to `delivery.request_delivery`.

## Authoring

**Purpose.** Problem: A domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code. Success metric: "human minutes from an owner's intent to a confirmed, compiled domain version", direction: down. Announcement: Domain owners now turn the workflow in their heads into a declared, checked domain without writing code. Every change shows what it breaks before anything is deployed.

**Roles.** owner, expert. In the world, owner is ana and expert is eli. The kernel (`external:kernel`) is the actor of the record_* actions listed below.

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
| review | enum: proposed, confirmed, unknown (initial: proposed) |
| value | string, optional |
| cites | string |
| issues | integer, optional |
| issue_summary | string, optional |

**DecisionRequest** — A decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox.
| Property | Type |
|---|---|
| subject | string |
| grounds | string |
| recommendation | string |
| stage | enum: open, decided (initial: open) |
| choice | string, optional |

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
| approved | boolean, optional |
| main | string, optional |
| stage | enum: recorded (initial: recorded) |
| last_evidence | string, optional |
| evidence_error | string, optional |

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

### Authoring links

| Link | From | To | Cardinality | Required |
|---|---|---|---|---|
| question | Answer | Question | many-to-one | yes |
| element | DecisionRequest | Element | many-to-one | no |
| parents | Commit | Commit | many-to-many | no |
| origin | Element | Source | many-to-one | no |

### Authoring actions

Actors: owner, expert, or `external:kernel`. A kernel service call names the service, its arguments, and the reply action that receives the result.

**add_source** — owner. Creates a Source. Params: kind (enum: repository, records, transcripts, interview-log); path (string); local_only (boolean, optional). Add a source of raw material: code, records, transcripts or the interview log.

**fetch_source** — owner. Target: Source. Fetch a link source into a snapshot, once. Effect: calls kernel service `fetch_source` with source = target.id; reply action `record_fetch`.

**record_fetch** — external:kernel. Target: Source. Param: sha256 (string). Records the fetched snapshot's hash. Effect: sets target.sha256 to params.sha256.

**ask_question** — owner. Creates a Question. Params: stage (string); text (string). Ask a question of the current stage's bundle.

**answer_question** — owner or expert. Creates an Answer. Params: question (reference to a Question); words (string); decisions (string). Answer a question, in the person's own words. Effect: calls kernel service `record_answer` with question = target.question.text, answer = target.words, decisions = target.decisions; reply action `record_answer_ref`.

**propose_element** — owner. Creates an Element. Params: path (string); origin (reference to a Source); cites (string); value (string). Propose a draft element that cites where it came from. Effect: calls kernel service `propose_element` with path = target.path, value = target.value, source = target.cites; reply action `record_proposal`.

**confirm_element** — owner. Target: Element. `requires: human` (only a person may take it). Confirm a drafted element. Only a person confirms. Effect: calls kernel service `confirm_element` with paths = target.path, approver = actor.id; reply action `record_confirmation`.

**mark_unknown** — owner or expert. Target: Element. Mark an element as not known yet, instead of guessing.

**request_decision** — owner. Creates a DecisionRequest. Params: element (reference to an Element); subject (string); grounds (string); recommendation (string). Ask the owner for a decision only a person may take, with grounds and a recommendation.

**decide** — owner. Target: DecisionRequest. Param: choice (string). `requires: human`; records a decision. Decide a requested decision. Effect: sets target.choice to params.choice.

**commit_draft** — owner. Target: Draft. Snapshot the working copy as an immutable commit. Cite its evidence on the commit with cite_evidence. Effect: calls kernel service `commit` with declaration = target.declaration; reply action `record_commit`.

**record_commit** — external:kernel. Creates a Commit. Params: seq (integer); content (string); interface (string); domain (string); branch (string); author (string). Record the commit the kernel made. Effect: sets target.domain_id to params.domain.

**check_commit** — owner. Target: Commit. Run the change check on a commit. Effect: calls kernel service `change_check` with domain = target.domain_id, commit = target.id; reply action `record_check`.
Preconditions:
| id | check | reason |
|---|---|---|
| not-approved | target.approved != true | An approved commit passed its check; check a new commit instead. |

**record_check** — external:kernel. Target: Commit. Params: passed (boolean); summary (string). Record the change check's result on the commit. Effect: sets target.checks_passed to params.passed and target.failing to params.summary.
Preconditions:
| id | check | reason |
|---|---|---|
| settled | target.approved != true | An approved commit's check is settled; a late result is not recorded. |

**approve_commit** — owner. Target: Commit. `requires: human`; records a decision. Approve a commit: merge it into main and tag it. Only a person approves. Effect: calls kernel service `approve_commit` with domain = target.domain_id, commit = target.id, approver = actor.id; reply action `record_approval`.
Preconditions:
| id | check | reason |
|---|---|---|
| checks-pass | target.checks_passed == true | Run the change check, and approve only a commit that passes it. |
| not-approved | target.approved != true | Already approved; approve a newer commit. |

**record_approval** — external:kernel. Target: Commit. Params: approved (boolean); main (string). Record the approval and what main points to. Effect: sets target.approved to params.approved and target.main to params.main.
Preconditions:
| id | check | reason |
|---|---|---|
| approved-only-if-checked | params.approved != true or target.checks_passed == true | A commit is recorded as approved only if its change check passed. |

**deliver** — owner. Target: Commit. Param: environment (enum: local). Ask Delivery to deliver an approved commit to an environment. It triggers the handoff described below.
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

**skip_stage** — owner. Target: Draft. `requires: human`. Params: stage (string); reason (string). Say an optional stage has nothing, in the owner's words. Effect: calls kernel service `skip_stage` with stage = params.stage, reason = params.reason; reply action `record_skip`.

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

**Human-only actions (requires: human):** confirm_element, decide, approve_commit, skip_stage, confirm_all_proposed.
**Actions that record a decision:** decide, approve_commit.

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
| proposed | mark_unknown | to unknown |
| proposed | record_proposal | to proposed |
| proposed | record_confirmation | n/a |
| unknown | confirm_element | to confirmed |
| unknown | mark_unknown | n/a |
| unknown | record_proposal | n/a |
| unknown | record_confirmation | n/a |
| confirmed | confirm_element | n/a |
| confirmed | mark_unknown | deny: "A confirmed element changes by a new proposal and a new commit, not by marking it unknown." |
| confirmed | record_proposal | n/a |
| confirmed | record_confirmation | to confirmed |

**DecisionRequest.stage** (initial: open)
| State | Action | Result |
|---|---|---|
| open | decide | to decided |
| decided | decide | deny: "Already decided; a new decision needs a new request." |

**Draft.stage** (initial: open). In state open, each of these actions goes to open: commit_draft, next_questions, record_questions, search, record_search, skip_stage, record_skip, merge_main, record_merge, checkout_commit, record_checkout, confirm_all_proposed, record_confirm_all.

**Commit.stage** (initial: recorded). In state recorded, each of these actions goes to recorded: check_commit, record_check, approve_commit, record_approval, deliver, record_evidence, cite_evidence.

**Answer.stage** (initial: recorded). In state recorded, record_answer_ref goes to recorded.

### Authoring invariants

| id | on | check | reason |
|---|---|---|---|
| approved-commits-passed-their-checks | Commit | target.approved != true or target.checks_passed == true | An approved commit passed its change check. |
| decided-requests-record-the-choice | DecisionRequest | target.stage != 'decided' or exists(target.choice) | A decided request records what was chosen. |
| fetched-sources-have-a-snapshot | Source | target.stage != 'fetched' or exists(target.sha256) | A fetched source has the hash of its snapshot. |
| elements-cite-a-source | Element | exists(target.origin) | Every element cites where it came from. |

### Authoring glossary

- **commit**: An immutable snapshot of the working copy. Every change is a new commit; nothing is edited in place.
- **main**: The protected branch. A commit reaches main only by being approved, and only commits on main are delivered.
- **approval**: A person's decision that merges a commit into main and tags it. It cannot be undone; a newer approved commit supersedes it.
- **element**: One part of a declaration (an object, a link, an action, a cell, an invariant), drafted by an agent and confirmed only by a person.
- **draft**: The working copy of a domain's declaration on a branch: what the next commit will snapshot.
- **change check**: The checks a commit runs before approval: structure, semantics, scenarios, harness, past actions, stranded objects.
- **unknown**: An element marked as not known yet, instead of guessed. It stays visible until someone answers it.

## Delivery

**Purpose.** Problem: An approved domain version must become working software in an environment, and nothing unverified may reach it. Success metric: "share of approved versions that reach verified-in-use without a manual fix or rollback", direction: up. Announcement: Approved domain versions now reach the environment as working software in one step. Nothing that fails its checks or lacks a person's approval gets there.

**Roles.** approver (in the world: ana). `system` is the actor of request_delivery; `external:kernel` is the actor of the record_* actions.

### Delivery objects

**DeliveryRequest** — A request to deliver an approved commit of a domain, handed off by Authoring.
| Property | Type |
|---|---|
| domain_id | string |
| commit | string |
| interface | string |
| environment | string |
| approver | string |
| build | string, optional |
| harness_ok | boolean, optional |
| deployed | boolean, optional |
| refusal | string, optional |
| verified | boolean, optional |
| stage | enum: requested, previewing, previewed, deploying, done, verified (initial: requested) |

**Environment** — Where a domain runs; it points at one deployed commit.
| Property | Type |
|---|---|
| name | string |
| current_commit | string, optional |

Delivery has no links.

### Delivery actions

**request_delivery** — system. Creates a DeliveryRequest. Params: domain_id, commit, interface, environment, approver (all strings). Receive a request to deliver an approved commit, handed off by Authoring.

**preview** — approver. Target: DeliveryRequest. Build the commit and run its harness, before anything is deployed. Effect: calls kernel service `preview` with domain = target.domain_id, commit = target.commit; reply action `record_build`.

**record_build** — external:kernel. Target: DeliveryRequest. Params: build (string); harness_ok (boolean). Record the build and its harness result. Effect: sets target.build to params.build and target.harness_ok to params.harness_ok.

**deploy** — approver. Target: DeliveryRequest. `requires: human`; records a decision. Deploy the commit, under the fixed floor. Only a person deploys. Effect: calls kernel service `deploy` with domain = target.domain_id, commit = target.commit, approver = actor.id; reply action `record_deployment`.
Preconditions:
| id | check | reason |
|---|---|---|
| harness-passed | target.harness_ok == true | Deploy only a build whose harness passed. |

**record_deployment** — external:kernel. Target: DeliveryRequest. Params: deployed (boolean); error (string). Record whether the deploy happened, or which floor rule refused it. Effect: sets target.deployed to params.deployed and target.refusal to params.error.

**verify** — approver. Target: DeliveryRequest. `requires: human`. Param: verified (boolean). Confirm the deployed domain works in use (the probes). Effect: sets target.verified to params.verified.
Preconditions:
| id | check | reason |
|---|---|---|
| deployed | target.deployed == true | Only a deployment that happened can be verified. |

Human-only actions: deploy, verify. Actions that record a decision: deploy.

### Delivery transitions

**DeliveryRequest.stage** (initial: requested)
| State | Action | Result |
|---|---|---|
| requested | preview | to previewing |
| requested | record_build | n/a |
| requested | deploy | deny: "Preview it first." |
| requested | record_deployment | n/a |
| requested | verify | n/a |
| previewing | preview | deny: "A preview is running." |
| previewing | record_build | to previewed |
| previewing | deploy | deny: "The preview has not finished." |
| previewing | record_deployment | n/a |
| previewing | verify | n/a |
| previewed | preview | to previewing |
| previewed | record_build | n/a |
| previewed | deploy | to deploying |
| previewed | record_deployment | n/a |
| previewed | verify | n/a |
| deploying | preview | deny: "A deploy is running." |
| deploying | record_build | n/a |
| deploying | deploy | deny: "A deploy is running." |
| deploying | record_deployment | to done |
| deploying | verify | n/a |
| done | preview | to previewing |
| done | record_build | n/a |
| done | deploy | to deploying |
| done | record_deployment | n/a |
| done | verify | to verified |
| verified | preview | n/a |
| verified | record_build | n/a |
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

The handoff target is target.domain_id + ':' + target.id + ':' + params.environment.

What the receiver needs: request_delivery takes domain_id, commit, interface, environment and approver, all strings, and creates a DeliveryRequest (stage requested).
