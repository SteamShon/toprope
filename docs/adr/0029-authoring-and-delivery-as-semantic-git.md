# ADR-0029: Authoring and Delivery as a semantic-diff git

- Link: ① iterate safely, ② model is right, ⑥ org productivity · Status: **proposed**
  (assistant draft of the researcher's decisions; implementation waits for acceptance) ·
  2026-11-04
- Builds on: ADR-0004 (provenance), ADR-0008 (domain interface, element hashes, versioning by
  diff), ADR-0009 (change check), ADR-0012 (event sourcing), ADR-0013 (impact report),
  ADR-0022 (two self domains), ADR-0024 (handoff, deploy floor), ADR-0026 (composition),
  ADR-0028 (kernel services)
- Would amend: ADR-0022 and the M1 scope document (the handoff contract fields, the version
  vocabulary), ADR-0026 (what a released system is), ADR-0028 (two services)

## Context
Writing the M1 gold set showed where Authoring's state was heading: version states such as
stale, withdrawn and rejected, and rules about which state each moves to and when. Each of
those adds matrix cells and questions, and each makes the owner re-review more than changed.
Git solves the same problem with fewer moving parts:
- immutable commits
- tags that mark a decision
- a diff that shows what changed
- deploys that point an environment at one commit

Toprope already has the parts that make this semantic rather than textual:
- element hashes and an interface diff (ADR-0008)
- an impact report (ADR-0013)
- a change check (ADR-0009)

## Decision (the researcher's, as handed off)
1. **Authoring is a commit log.**
   - One working copy per domain. There are no branches in M1.
   - Compiling the working copy makes an **immutable candidate commit**. Every later change
     is a new commit.
   - **Approve is an immutable tag on a commit.** It cannot be removed or undone. A wrong
     approval is superseded by approving a newer commit (the revert style).
   - There are no version states such as stale, withdrawn or rejected. A candidate that is
     not approved is simply a commit without an approval.
   - A candidate, its change report and its approval correspond to a pull request. The
     Proposal and Decision vocabulary is aligned to this in Phase A.
2. **The diff is semantic, and so is the review.**
   - **What is compared**: between two commits, the domain graph (objects, links,
     actions), the transition matrix cells and the invariants, by element (ADR-0008 hashes).
   - **What the owner re-confirms**: only the elements that changed directly. An element
     whose hash did not change keeps its confirmation.
   - **Indirect effects are reported, not re-reviewed.** Semantic conflicts, invariants,
     scenario regressions and the harness find them, and the change report lists them.
3. **Delivery chooses which commit runs.**
   - An environment holds a ref to the commit deployed there. A deploy moves that ref to one
     commit. There is one environment, local, in M1.
   - Deploy requests for one environment are processed in order.
   - Authoring's commits and approvals are independent of what is deployed.
   - The brake is Delivery's human deploy approval, never undoing an Authoring approval. A
     Delivery refusal does not undo an Authoring approval (as before, ADR-0024).
4. **Unchanged constraints.**
   - Events are never rewritten.
   - The deploy floor in code (`toprope-deploy`) cannot be weakened by a declaration.
   - Migrations, rollback and read-back stay in M2.

## Proposed details (assistant, for the researcher to accept or change)
- **A commit's identity.** A commit is identified by the content hash of its declaration
  (as `toprope-deploy` builds are today) plus a sequence number per domain. The declaration's
  `version` field becomes that sequence number, set when compiling, never by hand. Events
  record it in `domain_version` as now.
- **The diff's base.** The change check (ADR-0009) and the impact report (ADR-0013) compare a
  candidate with its parent commit. For an approval, they also compare it with the last
  approved commit: the owner sees what changed since the last approved commit.
- **Two kernel services** join the ADR-0028 catalog, so the generated Authoring tool can do
  this from its declaration:
  - `commit`: snapshot the working copy and return the commit id and sequence number
  - `diff`: between two commits, return the counts of changed elements and of elements to
    re-confirm, and a summary
- **The handoff carries a commit.** The delivery request's contract (scope document) carries
  the commit id instead of separate domain, representation and interface versions. The
  commit determines all three.
- **A released system** (ADR-0026) is the tuple of its members' commits.

## Open questions (not decided; to be answered before implementation)
1. **What counts as "changed directly".** Which reference changes make an element directly
   changed? For example, an action whose referenced object was renamed. Today's element hash
   counts any change in an element's own content, references included.
2. **When a cited Answer changes.** If an Answer that a confirmation cites changes, is that
   confirmation reopened?
3. **Branch and merge (an M2 candidate).** Element-level 3-way merge would stop direct
   conflicts, and running the change check on the merge result would stop indirect ones,
   with the merge commit approved as a new candidate. Is this the shape for M2?

## Affected ADRs, documents and code

| Item | Verdict | Why |
|---|---|---|
| ADR-0004 provenance, status per element | no impact | Confirmation stays per element; unchanged hashes carry it across commits |
| ADR-0008 interface, element hashes, version by diff | no impact (the basis) | The semantic diff is this diff |
| ADR-0009 change check | needs change | "the new version against the current one" becomes "a candidate against its parent, and against the last approved commit" |
| ADR-0012 event sourcing | no impact | Commits and tags are append-only |
| ADR-0013 impact report, cache | needs change (base only) | The impact report is the "indirect effects" report; its base is the parent commit |
| ADR-0014, ADR-0025 interview and stages | no impact | The interview edits the working copy. Compiling makes a commit |
| ADR-0018 migration | no impact | Still M2 |
| ADR-0020 world map, its diff in the report | no impact | The map diff is part of the semantic diff report |
| ADR-0022 two self domains, handoff contract | needs change | The request carries a commit. "Approving a version" becomes approving a commit |
| ADR-0024 handoff, deploy floor | no impact | Builds are already identified by the declaration's hash, and an environment already points at one build (`current.json`) |
| ADR-0026 composition | needs change (wording) | A released system is a tuple of member commits |
| ADR-0028 kernel services | needs change | Adds the `commit` and `diff` services |
| M1 scope document | needs change | Version vocabulary (`DomainVersion` becomes Commit and Approval), the handoff fields, "approving a version" |
| `docs/semantics.md` `domain_version` | no impact if the sequence-number proposal is accepted | Stays an integer, set by compiling |
| `decl/interface.py` `diff_interface` | no impact (reused) | Element-level added, removed, changed and text-only, with hashes |
| `deploy/` `LocalEnvironment` | needs change (small) | Records the commit id. It already holds one ref per environment |
| `authoring/` workspace | needs change (bootstrap only) | Compiling would make a commit, and confirmations would carry over by hash. The generated Authoring tool replaces it in M1 |
| `kernel/` catalog | needs change | `commit` and `diff` |
| M0a sub-PR 8 and 9 (not built yet) | needs change (spec wording) | The diff's base is the parent commit |
| `experiments/` instruments | not read, not touched | As requested |
