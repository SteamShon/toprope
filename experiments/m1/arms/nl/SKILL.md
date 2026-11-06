# Skill: working in the Authoring and Delivery domains (composition `toprope-self`)

Two domains are joined by one composition. **Authoring** turns a domain owner's workflow into a declared, checked, approved domain version (a commit on main). **Delivery** takes an approved commit and makes it working software in an environment. Authoring hands approved commits to Delivery; nothing else crosses between them.

The composition is named `toprope-self`, version 1. It has two members, authoring (interface 1) and delivery (interface 1), and one wire: Authoring's handoff `deliver_approved_commit` feeds Delivery's action `request_delivery`.

Three kinds of actor appear in the rules:
- **Roles** (people): owner and expert in Authoring; approver in Delivery.
- **The kernel** (`external:kernel`): a non-person actor that performs the "record_…" actions, writing down results of work the kernel did. An agent never takes these.
- **The system**: the actor of Delivery's `request_delivery`, which fires from the handoff.

"Only a person may take" an action is marked `requires: human` in the declarations. An agent may prepare and propose but must not take these actions itself; a person takes them. Those actions are listed in each domain below.

---

## Domain 1: Authoring

**Purpose.** A domain owner's workflow lives in people's heads; turning it into a declared domain, and changing it safely, takes code. Authoring lets owners do it without writing code, and every change shows what it breaks before anything is deployed. Success metric (goal: down): human minutes from an owner's intent to a confirmed, compiled domain version.

### Roles
| Role | Who in the sample world | May take |
|---|---|---|
| owner | ana | add_source, fetch_source, ask_question, answer_question, propose_element, confirm_element, mark_unknown, request_decision, decide, commit_draft, check_commit, approve_commit, deliver, next_questions, search, skip_stage, open_draft, merge_main, checkout_commit, confirm_all_proposed |
| expert | eli | answer_question, mark_unknown only |
| kernel (external) | – | the record_… actions |

### Objects and their properties

**Source** – where raw material lives. Properties: kind (repository, records, transcripts, interview-log), path, local_only (boolean), sha256 (optional), stage (added, fetched). Starts at `added`.

**Question** – a question in a stage's bundle, for the owner to answer. Properties: stage (text), text.

**Answer** – the owner's answer in their words; its decisions become proposed elements. Properties: words, decisions, ref (optional; where the answer sits in the interview log, so elements can cite it), stage (only `recorded`). Linked to the Question it answers (many answers to one question; required).

**Element** – one part of the draft declaration (an object, link, action, cell, invariant…), proposed by an agent or confirmed by a person. Properties: path, review (proposed, confirmed, unknown), value (optional), cites, issues (optional integer), issue_summary (optional). Starts at `proposed`. Linked to its origin Source (many elements to one source).

**DecisionRequest** – a decision only a person may take, proposed with grounds and a recommendation and sent to that person's outbox. Properties: subject, grounds, recommendation, stage (open, decided), choice (optional). Starts at `open`. Linked to the Element it concerns (many-to-one).

**Commit** – an immutable snapshot of the working copy on a branch. Properties: seq, content, branch, author (optional), message (optional), interface, domain_id, checks_passed (optional), failing (optional), approved (optional), main (optional; what main points to), stage (only `recorded`). Linked to its parent commits (many-to-many; a merge commit has two parents).

**Draft** – the working copy of a domain's declaration on a branch; what the next commit snapshots. Properties: domain_id, declaration, branch, stage (only `open`), current_stage (optional), bundle (optional), merging (optional), conflicts (optional integer).

### Actions

"Needs first" lists preconditions beyond the state rules in the transition tables below.

| Action | Who | Target / params | Needs first | What it changes |
|---|---|---|---|---|
| add_source | owner | kind, path, local_only (optional) | – | Creates a Source (stage added). |
| fetch_source | owner | a Source | Source not yet fetched | Asks the kernel to fetch the link into a snapshot, once; the kernel replies with record_fetch. |
| record_fetch | kernel | Source; sha256 | Source is in `added` | Sets sha256; Source becomes `fetched`. |
| ask_question | owner | stage, text | – | Creates a Question for the current stage's bundle. |
| answer_question | owner or expert | question, words, decisions | – | Creates an Answer; sends question text, words and decisions to the kernel, which replies with record_answer_ref. |
| record_answer_ref | kernel | Answer; ref | – | Sets the answer's ref (its place in the interview log). |
| propose_element | owner | path, origin (a Source), cites, value | – | Creates an Element (proposed); asks the kernel to write it into the working copy; reply is record_proposal. |
| record_proposal | kernel | Element; issues, summary | element is `proposed` | Sets issues and issue_summary (records whether the element was written into the working copy). Stays `proposed`. |
| confirm_element | owner, **person only** | an Element | element is `proposed` or `unknown` | Kernel asked to confirm the path, with the actor as approver; reply record_confirmation. Element becomes `confirmed`. |
| record_confirmation | kernel | Element; confirmed list | element is `confirmed` | Records that the working copy holds the element as confirmed; stays `confirmed`. |
| mark_unknown | owner or expert | an Element | element is `proposed` | Marks the element as not known yet, instead of guessing; becomes `unknown`. |
| request_decision | owner | element, subject, grounds, recommendation | – | Creates a DecisionRequest (open) to send to a person. |
| decide | owner, **person only**, recorded as a decision | a DecisionRequest; choice | request is `open` | Sets choice; request becomes `decided`. |
| open_draft | owner | domain_id, declaration, branch | – | Creates a Draft (open) so the declaration can be interviewed, committed and checked. |
| next_questions | owner | a Draft | – | Asks the kernel for the current stage's bundle; reply record_questions. |
| record_questions | kernel | Draft; stage, bundle, questions | – | Sets current_stage and bundle. |
| search | owner | a Draft; query | – | Searches the sources (redacted; local-only sources are never served); kernel replies with record_search so the result is on record. |
| record_search | kernel | Draft; refs | – | Records which source chunks the search returned. |
| skip_stage | owner, **person only** | a Draft; stage, reason | – | Says an optional stage has nothing, in the owner's words; kernel replies record_skip. |
| record_skip | kernel | Draft; skipped | – | Records that the stage was skipped. |
| merge_main | owner | a Draft | – | Brings main into the branch's working copy and lists conflicts to resolve; the next commit records both parents. Reply record_merge. |
| record_merge | kernel | Draft; merge, conflicts, paths | – | Sets merging and conflicts. |
| checkout_commit | owner | a Draft; commit | – | Loads a commit into the working copy, to revert to it or build on it; committing it makes a new commit. Reply record_checkout. |
| record_checkout | kernel | Draft; content | – | Records that the working copy holds the commit's content. |
| confirm_all_proposed | owner, **person only** | a Draft | – | Confirms every element still proposed in the working copy, as right (kernel asked with path "all"; reply record_confirm_all). |
| record_confirm_all | kernel | Draft; confirmed list | – | Records which elements were confirmed. |
| commit_draft | owner | a Draft | – | Snapshots the working copy as an immutable commit via the kernel; reply record_commit. |
| record_commit | kernel | seq, content, interface, domain, branch, author | – | Creates the Commit (recorded) and sets its domain_id. |
| check_commit | owner | a Commit | commit is not already approved (`not-approved`: an approved commit passed its check; check a new commit instead) | Runs the change check; reply record_check. |
| record_check | kernel | Commit; passed, summary | – | Sets checks_passed and failing (the summary). |
| approve_commit | owner, **person only**, recorded as a decision | a Commit | `checks-pass`: checks_passed is true (run the change check; approve only a commit that passes). `not-approved`: not already approved (approve a newer commit). | Merges the commit into main and tags it; kernel is told the domain, commit and approver; reply record_approval. |
| record_approval | kernel | Commit; approved, main | `approved-only-if-checked`: may record approved=true only if checks_passed is true | Sets approved and main (what main points to). |
| deliver | owner | a Commit; environment (only `local`) | `approved`: the commit is approved (only an approved commit is delivered) | Triggers the handoff to Delivery (see below). |

### Transitions and what is not allowed in each state

Every cell not listed as a move or a denial is `n/a`: the action does not apply in that state.

**Source (field stage; starts `added`)**
| State | fetch_source | record_fetch |
|---|---|---|
| added | stays added (request sent) | moves to fetched |
| fetched | **denied**: a link is fetched once into a snapshot; add a new source to read it again | n/a |

**Element (field review; starts `proposed`)**
| State | confirm_element | mark_unknown | record_proposal | record_confirmation |
|---|---|---|---|---|
| proposed | → confirmed | → unknown | stays proposed | n/a |
| unknown | → confirmed | n/a | n/a | n/a |
| confirmed | n/a | **denied**: a confirmed element changes by a new proposal and a new commit, not by marking it unknown | n/a | stays confirmed |

**DecisionRequest (field stage; starts `open`)**
| State | decide |
|---|---|
| open | → decided |
| decided | **denied**: already decided; a new decision needs a new request |

**Draft (stage always `open`)**: commit_draft, next_questions, record_questions, search, record_search, skip_stage, record_skip, merge_main, record_merge, checkout_commit, record_checkout, confirm_all_proposed and record_confirm_all are all allowed and leave it `open`.

**Commit (stage always `recorded`)**: check_commit, record_check, approve_commit, record_approval and deliver are allowed in `recorded` and leave it `recorded`; their further limits are the preconditions in the action table (approval state lives in the approved/checks_passed properties, not the stage).

**Answer (stage always `recorded`)**: record_answer_ref is allowed and leaves it `recorded`.

### Invariants (always true)
1. **approved-commits-passed-their-checks**: a commit with approved = true has checks_passed = true.
2. **decided-requests-record-the-choice**: a DecisionRequest in stage `decided` has a choice.
3. **fetched-sources-have-a-snapshot**: a Source in stage `fetched` has a sha256.
4. **elements-cite-a-source**: every Element has an origin Source.

### Rules of conduct that follow
- An agent proposes elements (always with an origin source and a citation); only a person confirms (`confirm_element`, `confirm_all_proposed`), decides, approves a commit, or skips a stage.
- When something is not known, mark it unknown rather than guess. It stays visible until someone answers it.
- Every change is a new commit; nothing is edited in place. Approval cannot be undone; a newer approved commit supersedes it.
- Only commits on main are delivered, and a commit reaches main only by approval.

### Sample world (for reference by examples)
Actors: owner ana, expert eli. Sources: S-code (repository, src/toprope, added), S-docs (records, docs, fetched, sha256 5f1c). Question Q1 (stage purpose: "What problem does this domain solve, and for whom?") with Answer A1. Elements: E1 (path purpose, origin S-docs, proposed), E2 (objects.Commit, origin S-code, confirmed), E3 (actions.mark_unknown, origin S-docs, unknown). DecisionRequest DR1 (on E1; "Which success metric?"; grounds: the scope document names two; recommendation: human minutes to a confirmed version; open). Draft D1 (authoring, branch work). Commits on branch work: C1 (seq 1, interface 1.0.0, checks passed, approved, main C1), C2 (seq 2, 1.1.0, checks failed, not approved), C3 (seq 3, 1.2.0, checks passed, not approved).

---

## Domain 2: Delivery

**Purpose.** An approved domain version must become working software in an environment, and nothing unverified may reach it. Success metric (goal: up): share of approved versions that reach verified-in-use without a manual fix or rollback. Approved versions reach the environment in one step; nothing that fails its checks or lacks a person's approval gets there.

### Roles
| Role | Who | May take |
|---|---|---|
| approver | ana | preview, deploy (person only), verify (person only) |
| system | – | request_delivery (from the handoff) |
| kernel (external) | – | record_build, record_deployment |

### Objects
**DeliveryRequest** – a request to deliver an approved commit of a domain, handed off by Authoring. Properties: domain_id, commit, interface, environment, approver, build (optional), harness_ok (optional), deployed (optional), refusal (optional), verified (optional), stage (requested, previewing, previewed, deploying, done, verified). Starts at `requested`.

**Environment** – where a domain runs; it points at one deployed commit. Properties: name, current_commit (optional). There are no declared links in this domain.

### Actions
| Action | Who | Needs first | What it changes |
|---|---|---|---|
| request_delivery | system | – | Creates a DeliveryRequest from domain_id, commit, interface, environment, approver. |
| preview | approver | state allows it (see table) | Builds the commit and runs its harness, before anything is deployed; a preview changes no environment. Kernel replies with record_build. Stage → previewing. |
| record_build | kernel | stage is previewing | Sets build and harness_ok. Stage → previewed. |
| deploy | approver, **person only**, recorded as a decision | `harness-passed`: harness_ok is true (deploy only a build whose harness passed); stage allows it | Deploys the commit under the fixed deploy floor, passing the actor as approver; kernel replies with record_deployment. Stage → deploying. |
| record_deployment | kernel | stage is deploying | Sets deployed and refusal (the error, i.e. which floor rule refused it). Stage → done. |
| verify | approver, **person only** | `deployed`: deployed is true (only a deployment that happened can be verified) | Sets verified. Stage → verified. |

**Deploy floor** – rules the kernel enforces on every deploy that no declaration can weaken: approved, on main, not a downgrade, harness passed, a person deploys, nothing stranded. A refused deploy ends `done` with deployed = false and the refusal reason recorded.

### Transitions (field stage)
| State | preview | record_build | deploy | record_deployment | verify |
|---|---|---|---|---|---|
| requested | → previewing | n/a | **denied**: preview it first | n/a | n/a |
| previewing | **denied**: a preview is running | → previewed | **denied**: the preview has not finished | n/a | n/a |
| previewed | → previewing (preview again) | n/a | → deploying | n/a | n/a |
| deploying | **denied**: a deploy is running | n/a | **denied**: a deploy is running | → done | n/a |
| done | → previewing (retry) | n/a | → deploying (redeploy) | n/a | → verified |
| verified | n/a | n/a | n/a | n/a | **denied**: already verified |

Note that in `done`, verify is allowed by the table but still needs deployed = true; a refused deploy cannot be verified, but can be retried by previewing again.

### Invariants
1. **deployed-builds-passed-their-harness**: deployed = true implies harness_ok = true.
2. **verified-requests-were-deployed**: stage `verified` implies deployed = true.
3. **finished-deploys-record-the-outcome**: stage `done` or `verified` implies deployed has a recorded value (true or false).
4. **deploying-builds-passed-their-harness**: stage `deploying` implies harness_ok = true.

### Sample world
Environment ENV-local (name local). Approver ana. Requests (all environment local, approver ana): R1 (authoring, commit 2-c3d4, interface 1.1.0, requested); R2 (authoring, commit 3-e5f6, 1.1.0, previewed, build b2, harness failed); R3 (authoring, commit 4-a7b8, 1.2.0, done, build b3, harness passed, deployed false, refusal "stranded: E-live (state 'ended' is gone)"); R4 (delivery, commit 5-c9d0, 1.0.0, done, build b4, harness passed, deployed true, no refusal).

---

## Handoff: Authoring → Delivery

**Trigger.** When Authoring's `deliver` action succeeds (outcome ok). The commit must already be approved; `deliver` itself refuses otherwise, and the only environment it accepts is `local`.

**Sent** to Delivery interface 1.x, action `request_delivery`:
| Delivery param | Taken from |
|---|---|
| domain_id | the commit's domain_id |
| commit | the commit's id |
| interface | the commit's interface version |
| environment | the environment chosen in `deliver` |
| approver | the id of the person who took `deliver` |

The handoff's target key is `domain_id:commit:environment`.

**Receiver needs.** Delivery creates a DeliveryRequest in `requested`. From there a person (approver) must preview, then deploy, then verify. Delivery does not trust the handoff alone: the deploy floor requires the commit be approved, on main, not a downgrade, harness passed, deployed by a person, and with nothing stranded. Authoring's approval and passing change check are what make a commit eligible; Delivery's harness and floor decide whether it actually deploys.

---

## Glossary
| Term | Meaning |
|---|---|
| commit | An immutable snapshot of the working copy. Every change is a new commit; nothing is edited in place. |
| main | The protected branch. A commit reaches main only by being approved, and only commits on main are delivered. |
| approval | A person's decision that merges a commit into main and tags it. It cannot be undone; a newer approved commit supersedes it. |
| element | One part of a declaration (an object, a link, an action, a cell, an invariant), drafted by an agent and confirmed only by a person. |
| draft | The working copy of a domain's declaration on a branch: what the next commit will snapshot. |
| change check | The checks a commit runs before approval: structure, semantics, scenarios, harness, past actions, stranded objects. |
| unknown | An element marked as not known yet, instead of guessed. It stays visible until someone answers it. |
| delivery request | A request, handed over from Authoring, to put one approved commit of a domain into an environment. |
| preview | Building a commit and running its harness before anything is deployed; a preview changes no environment. |
| deploy floor | Rules the kernel enforces on every deploy that no declaration can weaken: approved, on main, not a downgrade, harness passed, a person deploys, nothing stranded. |
| verified | A deployment a person has checked in use, after it happened. |
