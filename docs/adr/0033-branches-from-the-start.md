# ADR-0033: Branches from the start

- Link: ① iterate safely, ④ shared language, ⑥ org productivity · Status: accepted · 2026-11-05 ·
  decided by: SteamShon (drafted by the assistant at the researcher's request)
- Supersedes: ADR-0029 resolved question 3 ("branch and merge: not in M1") and ADR-0032's
  branch row
- Builds on: ADR-0029 (commits, approval tags, semantic diff), ADR-0032 (the git/GitHub mapping)

## Context
ADR-0029 kept M1 to one working copy per domain and left branch and merge to M2. Commits
already record their parents as a list, so merge commits need no migration. The researcher
now wants branches from the start: several people or agents can work on a domain at once,
and a change can be tried without touching what is approved.

## Decision
1. **A branch is a named ref to a commit.** Each branch has its own working copy. `main`
   exists from the first commit.
2. **`main` is protected.**
   - A commit reaches `main` only by a **merge**.
   - Approval is a tag on a commit that `main` reaches; it is never on a branch-only commit.
   - "Approve" means "merge this branch into `main`, and tag the result approved", like
     merging a reviewed pull request into a protected branch.
3. **Merge is semantic and has two layers.**
   - **Direct conflicts.** The merge base is the nearest common ancestor in the commit
     graph. A 3-way merge works per element, by review hash: an element changed on only one
     side takes that side. An element changed differently on both sides is a **conflict**.
     Conflicts are listed by element and resolved in the working copy, as interview
     questions.
   - **Indirect conflicts.** The change check runs on the merge result (semantic conflicts,
     invariants, scenarios, harness), as with any commit.
   - The merge commit has two parents and is approved like any commit on `main`.
4. **Still no pull-request object** (ADR-0032).
   - A branch's review is derived: the semantic diff from the merge base to the branch
     head, its change report, and its check records.
   - A branch that is never merged is simply an unmerged branch. There are no open, merged
     or closed states.
5. **Delivery deploys only approved commits on `main`.** The deploy view is the semantic
   diff from the deployed commit to the commit being deployed: every change since the last
   deploy. The person reviews it and confirms.
6. **Ancestry, not sequence numbers, decides "newer".**
   - "Superseded" and "downgrade" (ADR-0029) compare commits on `main` by ancestry. A commit
     that is an ancestor of the deployed one is a downgrade.
   - Sequence numbers stay unique per domain, for reference only.

## Why there is no pull-request object
Everything a pull request holds already exists, derived from the branch and `main`:
- the diff: merge base to branch head
- the checks: check records on the branch head
- the discussion: questions on elements (ADR-0032)
- the review request: a decision request
- the approval: the merge into `main` and its tag

A stored PR object would add a second source of truth. Its state (open, merged, closed,
which head was reviewed) can drift from the refs, and every move of a ref would have to keep
it in sync. ADR-0029's review hash already pins which content was reviewed. The derived
review view costs nothing to add later as a stored record, if probes show it is needed: for
example, a description of intent that spans several commits, or a review aimed at a target
other than `main`.

## Consequences
- **The commit store** gains branch refs (append-only ref moves, under the domain lock), a
  merge base, an element-level 3-way merge with a conflict list, and `merge`/`branch`
  kernel services. The deploy floor switches from sequence numbers to ancestry on `main`.
  This is one M0a sub-PR.
- **The self domains' declarations** (Phase A) model branches, merges and conflicts. That is
  more Authoring vocabulary: Branch, Merge, Conflict.
- **Probes.** A probe can check that an agent never merges into `main` on its own.

## Resolved (researcher, 2026-11-05)
- **`main` is protected; approval means merge into `main`.** Commits are never approved on
  other branches.
- **Delivery deploys only from `main` in M1.** Isolated preview environments are revisited
  together with multiple environments. If added, they need their own store, recording
  receivers and a RecordingKernel, and P05's "deploy" is scoped to production environments.
  The side effects that led to this:
  - **The floor.** A branch commit is not approved, so a preview deploy deploys an
    unapproved commit. Probe P05 then holds only if "deploy" means production environments.
  - **State.** A preview needs its own event store. A shared store would hold events written
    under a schema `main` never had.
  - **Handoffs and kernel calls.** A preview domain would send real handoffs to real receivers
    and call real kernel services. It must be wired to recording receivers and a
    RecordingKernel instead.
  - **Data.** Copying production data into a preview carries redaction and local-only rules
    with it.
  - **Lifecycle.** Preview environments pile up and need cleanup.
  - **The existing `preview`** (build, harness, world map, no deploy) already gives most of
    the review value without these.
