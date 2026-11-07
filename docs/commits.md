# Commits: Authoring and Delivery as a semantic-diff git

Link: ① ② ④ ⑥. ADR-0029, ADR-0033. Authoring is an immutable commit log with branches and
approval tags. Delivery points an environment at one commit on `main`. Only what changed
directly is reviewed again.

Changes are actions of the Authoring domain, taken with `toprope-run` (the commands are in
[`workflow.md`](workflow.md) and the Authoring guide); reads are `toprope-commits`
([`kernel-commands.md`](kernel-commands.md)). `$R` is the `toprope-run` prefix from `workflow.md`
with `--member authoring`, and `D` the draft's id:

```bash
$R commit_draft D                    # a commit on the draft's branch (`work` by default)
$R check_commit 2-cd34…              # the change check, recorded on the commit
$R approve_commit 2-cd34…            # merge into main and tag; only a person
$R merge_main D                      # bring main in when approve reports conflicts;
$R commit_draft D                    #   the next commit records both parents
$R checkout_commit D --commit 1-ab12…   # load a commit; committing it reverts
uv run toprope-commits branches DOMAIN                       # every branch and its commit
uv run toprope-commits diff DOMAIN 1-ab12… 2-cd34…           # what changed directly
uv run toprope-commits log DOMAIN action:launch_experiment   # an element's history
```

## Commits
- **Evidence.** A commit cites what the change rests on after it is made, with `cite_evidence`
  (see *Evidence* below). Commit `5-c8fd1b8fc98be17c` of the Authoring domain still carries the
  free strings the `commit` service took before (#117), as `evidence` on its record.
- **Content-addressed and append-only.** A commit's content is the hash of the canonical
  declaration without `version`, plus its representations: the `*.representation.yaml` files
  next to the declaration whose `targets.domain` is this domain. Its id is `<seq>-<content>`, and
  reading it sets `version` to the sequence number.
  - Committing content identical to the head makes no new commit.
  - Returning to an earlier content makes a new commit that shares the stored object.
- **Parents are a list**: one parent, or two for a merge commit.
- **Interface version.** Each commit records its derived interface version (ADR-0008):
  removed or changed elements bump major, added elements minor, text-only changes patch.
- **Storage.** The store lives under `<workspace>/.toprope/commits/<domain>/` and **is kept in
  git** (decided by the researcher, 2026-11-06): commits, branches, approvals and check records
  are decisions, so they are shared and audited like code. The rest of `.toprope/` (caches,
  snapshots, environments, reports) stays local. Writes take a per-domain file lock.
- **Per-domain layout** (ADR-0037). Everything about one domain lives under
  `domains/<domain>/`: its declaration, its generated guide, its interview log, and, when it
  runs, its event log (`jsonl:domains/<domain>/events`, an append-only store kept in git).

## Author, history and checkout (ADR-0032)
- **Author.** A commit records who compiled it: `commit --as NAME`, or the calling actor
  when the kernel's `commit` service runs. A merge commit is authored by its approver.
- **An element's history**, like `git log -- path`: `log <element key>` lists the commits
  that added, changed or removed the element, or changed its provenance (a confirmation,
  or a new source). Each entry has the author, the message, and the `source` and `status`
  the element cites. It reads from what `main` points to (else the `work` head), or
  `--at <commit>`. A merge commit is listed only when the element differs from every
  parent, so a change that came in from `main` is credited where it was made.
- **Checkout.** `checkout <commit>` (or the kernel's `checkout` service) loads a commit's
  declaration and representations into the working copy, keeping the draft's `version`.
  Committing it makes a new commit, so a revert is a commit. It is refused when the working
  copy holds content no commit has, unless `--force`, which also recovers a working copy
  that no longer parses. Files are written under temporary names and then renamed.

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
- **Resolving conflicts.** `merge` writes the 3-way merge into the working copy and lists the
  conflicts. At a path conflict the branch's value is kept. At an element conflict the
  element holds both sides' changes, field by field, for you to judge. An element both
  sides changed is not listed again when the merge kept your version whole, because its path
  conflicts already show every change from `main`. Resolve them, then `commit
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

## Check records (ADR-0032)
`change-check` runs the change check on a commit and records the result on it, one record
per check plus the whole; a preview records its harness. See [`change-check.md`](change-check.md).

## Evidence (ADR-0041)
A commit may cite the evidence for its change, through the kernel's `cite_evidence` service
or `CommitStore.cite`. Evidence is a pointer that must resolve, never prose. A claim with no
pointer is refused. Each kind has a strength, which says how far the evidence goes:

| Kind | Ref | Must resolve to | Strength |
|---|---|---|---|
| `interview` | a chunk of an interview-log source | a line the owner said | pointed |
| `source` | a chunk of any other source | a line in the code or the records | pointed |
| `check` | a check name, e.g. `change-check` | a check recorded on this commit | ran |
| `event` | `<stream>@<version>` | an event in the deployed domain's store | observed |
| `approval-run` | a GitHub Actions run URL | a human request approved in that run (ADR-0039), recorded in `.toprope/approval-runs.jsonl` | approved |

The `human-request` workflow appends each approved run to `.toprope/approval-runs.jsonl` with
the result it pushes, so the record outlives the branch and a squash merge.
Citations are appended to `evidence.jsonl` next to the commit log, with who cited and when,
and are never rewritten. `toprope-commits evidence DOMAIN COMMIT` lists them. Nothing requires
evidence yet. In the Authoring domain, the owner or their agent cites with the action
`cite_evidence` on a commit that is not approved yet. Its reply `record_evidence` keeps the
last strength, or why the ref was refused, on the Commit. A rule such as "approve only with
evidence that ran" is a later decision.

## Approval
An approval is an immutable tag on a commit `main` points to. Tagging again is a no-op. A
wrong approval is superseded by approving a newer commit. The kernel's `approve_commit`
refuses unless the calling person is the approver, and returns the commit `main` points to.
`main` takes no unconfirmed proposal (ADR-0041): approving a commit, or the merge it makes, is
refused while it holds any element with `status: proposed`, and the change check records how
many are left (the `confirmed` check record). The kernel's `change_check` service reports
`passed: false` with `confirmed` among `failing` while any are left, so a declaration that
approves only commits whose checks passed refuses them too. A cell's per-role parts
(`by_role`) count as the cell: confirming the cell confirms them. Deploy refuses a commit that
holds proposed elements as a backstop. Drafts and previews still compile and test them.

`commit` also reports `last_approved`, so a declaration can ask `diff` what changed since
the last approved commit.

## Delivery
`LocalEnvironment.deploy_commit` (or the `deploy` kernel service, which Delivery's `deploy` action calls) is
the only way to move an environment's ref to a commit, under a per-environment lock. Only
commits on `main` are deployed (ADR-0033); ancestry, not sequence numbers, decides what is
newer. Besides the build floor (untainted, the harness passed, a person approves, nothing
stranded), it refuses a commit that is:
- **unapproved**: no approval on `main` (every branch-only commit)
- **superseded**: not what `main` points to
- a **downgrade**: the deployed commit or one of its ancestors (rollback comes in M2)
- not yet built: preview it first

A deploy is also recorded with the commits, in `deployments.jsonl` (ADR-0045). With
`--kernel-root`, `toprope-run` and `toprope-server --composition` run each member's deployed
commit, else its approved `main`; `--working-copy` runs the files instead.
