# Commits: Authoring and Delivery as a semantic-diff git

Link: ① ② ④ ⑥. ADR-0029, ADR-0033. Authoring is an immutable commit log with branches and
approval tags. Delivery points an environment at one commit on `main`. Only what changed
directly is reviewed again.

```bash
uv run toprope-author commit -m "add launch rules"   # a commit on the `work` branch
uv run toprope-author commit --branch launch-rules   # or on a branch of your own
uv run toprope-author diff 1-ab12… 2-cd34…           # what changed directly
uv run toprope-author approve 2-cd34… --as ana       # merge into main and tag; only you
uv run toprope-author merge --branch launch-rules    # bring main in when approve reports conflicts
uv run toprope-author commit --branch launch-rules --merge 3-ef56…   # record the resolution
uv run toprope-author branches                       # every branch and its commit
```

## Commits
- **Content-addressed and append-only.** A commit's content is the hash of the canonical
  declaration without `version`, plus its representations: the `*.representation.yaml` files
  next to the declaration whose `targets.domain` is this domain. Its id is `<seq>-<content>`, and
  reading it sets `version` to the sequence number.
  - Committing content identical to the head makes no new commit.
  - Returning to an earlier content makes a new commit that shares the stored object.
- **Parents are a list**: one parent, or two for a merge commit.
- **Interface version.** Each commit records its derived interface version (ADR-0008):
  removed or changed elements bump major, added elements minor, text-only changes patch.
- **Storage.** The store lives under `<workspace>/.toprope/commits/<domain>/`. Keep
  `.toprope/` out of version control. Writes take a per-domain file lock.

## Branches (ADR-0033)
- **A branch is a named ref to a commit.** A commit goes onto a branch (`work` by default).
  A new branch starts from `main`. Before the first approval, it starts from the domain's
  first commit, so every branch shares a base. Ref moves are appended to `refs.jsonl` under
  the domain lock. A store written before branches gets its refs derived once: `work` is the
  last commit, and `main` the newest approved one.
- **`main` is protected.** Only `approve` moves it, so approving means merging into `main`.
  If `main` has not moved since the branch left it, `main` fast-forwards to the commit.
  Otherwise a merge commit with two parents (main, the commit) is made. The tag goes on what
  `main` then points to. A commit `main` already contains cannot be approved: approve a
  newer one.
- **The merge is semantic**, from the nearest common ancestor:
  - **By element.** An element (by review hash) changed differently on both sides is a
    **conflict** (`element:<key>`), even when the two sides changed different fields of it.
    This includes an element added on both sides with different content.
  - **By path**, inside the declaration. A path changed on one side takes that side. A path
    changed differently on both sides is a conflict too, listed with its base, ours and
    theirs. Elements with ids (scenarios, invariants) merge by id; lists of names (roles)
    merge as sets.
  - **What `main` takes must validate**, on a fast-forward as well as on a merge commit. This
    catches indirect conflicts, where each side is valid alone but not together. The full
    change check (M0a sub-PR 8) will run there too.
- **Resolving conflicts.** `merge` writes the 3-way merge into the working copy, keeping the
  branch's value at each conflict, and lists the conflicts. Resolve them, then `commit
  --merge <main>` records both parents. Approving that commit is a fast-forward.
- **No pull-request object.** A branch's review is derived: the diff from the merge base,
  its change report and its check records. `commit` reports `to_review` since the merge base
  with `main`, so changes that others landed on `main` are not yours to re-confirm.

## What is reviewed again
The **review hash** of an element covers everything it says, references and wording
included, except provenance (`source`, `status`). Confirming an element changes nothing.
- **Changed directly**: an element whose review hash changed. These, and new elements, are
  `to_review`. A rename makes every element that references it direct.
- **Indirect effects** are reported by the change check, not re-reviewed. A confirmation
  that cites a superseded answer is reported too, not reopened.
- **Beyond the interface.** The diff also covers what the interface does not: roles, each
  object's stage field and initial stage, handoffs, scenarios, fixtures and purpose.

## Approval
An approval is an immutable tag on a commit `main` points to. Tagging again is a no-op. A
wrong approval is superseded by approving a newer commit. The kernel's `approve_commit`
refuses unless the calling person is the approver, and returns the commit `main` points to.

`commit` also reports `last_approved`, so a declaration can ask `diff` what changed since
the last approved commit.

## Delivery
`LocalEnvironment.deploy_commit` (or the `deploy` kernel service, or `toprope-deploy deploy`) is
the only way to move an environment's ref to a commit, under a per-environment lock. Only
commits on `main` are deployed (ADR-0033); ancestry, not sequence numbers, decides what is
newer. Besides the build floor (untainted, the harness passed, a person approves, nothing
stranded), it refuses a commit that is:
- **unapproved**: no approval on `main` (every branch-only commit)
- **superseded**: not what `main` points to
- a **downgrade**: the deployed commit or one of its ancestors (rollback comes in M2)
- not yet built: preview it first
