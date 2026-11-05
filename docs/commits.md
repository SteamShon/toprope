# Commits: Authoring and Delivery as a semantic-diff git

Link: ① ② ⑥. ADR-0029. Authoring is an immutable commit log with approval tags. Delivery
points an environment at one commit. Only what changed directly is reviewed again.

```bash
uv run toprope-author commit -m "add launch rules"   # compile the working copy into a commit
uv run toprope-author diff 1-ab12… 2-cd34…           # what changed directly
uv run toprope-author approve 2-cd34… --as ana       # only you; immutable
```

## Commits
- **Content-addressed and append-only.** A commit's content is the hash of the canonical
  declaration without `version`, plus its representations: the `*.representation.yaml` files
  next to the declaration whose `targets.domain` is this domain. Its id is `<seq>-<content>`, and
  reading it sets `version` to the sequence number.
  - Committing content identical to the head makes no new commit.
  - Returning to an earlier content makes a new commit that shares the stored object.
- **Parents are a list**: one parent in M1, so merge commits can come in M2 without
  migration.
- **Interface version.** Each commit records its derived interface version (ADR-0008):
  removed or changed elements bump major, added elements minor, text-only changes patch.
- **Storage.** The store lives under `<workspace>/.toprope/commits/<domain>/`. Keep
  `.toprope/` out of version control. Writes take a per-domain file lock.

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
An approval is an immutable tag. Tagging again is a no-op. A wrong approval is superseded by
approving a newer commit. The kernel's `approve_commit` refuses unless the calling person is
the approver.

`commit` also reports `last_approved`, so a declaration can ask `diff` what changed since
the last approved commit.

## Delivery
`LocalEnvironment.deploy_commit` (or the `deploy` kernel service, or `toprope-deploy deploy`) is
the only way to move an environment's ref
to a commit, under a per-environment lock. Besides the build floor (untainted, the harness
passed, a person approves, nothing stranded), it refuses a commit that is:
- **unapproved**
- **superseded** by a newer approved commit
- a **downgrade**: not newer than the deployed one (rollback comes in M2)
- not yet built: preview it first
