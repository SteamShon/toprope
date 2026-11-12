# ADR-0055: Experiment run records live outside the working tree

- Link: none (an enabler: where experiment evidence lives) · Status: **accepted**, 2026-11-12,
  decided by SteamShon. The researcher noticed the cost on a `git pull` and asked whether raw run
  records belong in git. They chose the recommendation ("만들어줘"). Drafted by the assistant.
- Amends: how `experiments/*/runs/` is kept. Builds on: ADR-0040 and ADR-0047 (M1 Phase B's
  records), ADR-0054 (M2).

## Context
M1's Phase B wrote every arm's outputs, the probe worlds and the grader's transcripts into
`experiments/m1/runs/` and committed them: about 684 MB and 27,700 files in the working tree. Git
compresses them to about 200 MB. Every clone, pull and cloud session carries them, though almost
nobody reads them. Only the scorer and the grader's validation read them.

They are evidence for preregistered experiments, so they must stay recoverable, unchanged and
traceable to what was scored. They need not stay in the working tree.

Removing files from the tree does not shrink git's history. Rewriting the history of `develop` or
`main` is not allowed (AGENTS.md). So M1's records stay in history, and the decision is about the
tree and about what later milestones commit.

## Decision
1. **What stays in git:** a run's summary. That is its top-level files (manifests, noise reports,
   the run log) and each `scoring*/` directory's own files (the blind labels, the confirmed labels,
   the metrics). Reports and verdicts cite these.
2. **What leaves the tree:** a run's raw records. These are the arms' outputs, the worlds, and the
   grader's transcripts (`scoring*/transcripts/`).
3. **M1, already in history:**
   - `tools/run_archive.py split` removes the raw directories from the tree.
   - It records the commit that holds them, and each directory's git tree hash, in the run's
     `RAW.json`.
   - It adds a `.gitignore`, so a restored copy is not committed again.
   - `restore` brings the records back from that commit and checks the tree hashes.
   - Split now: `superseded/`, `phase-b/`, `phase-b-combined/` and `phase-b-recheck/`.
   - `phase-b-recheck-combined/` stays whole until M2's grader is frozen, because a grader
     revision may read it again.
4. **M2 on, never committed:**
   - Raw records are written outside the repository.
   - `run_archive.py pack` makes a reproducible `.tar.gz` and a manifest that holds the archive's
     sha256 and every file's sha256. The manifest is committed.
   - The archive is uploaded as a GitHub release asset, and the manifest names its URL.
   - `fetch` downloads it and checks both levels of hash.
5. **Enforced:**
   - The `checks` workflow runs `run_archive.py check`. It fails if a raw path is tracked again or
     not ignored.
   - Phase B's commands refuse a split run whose raw records are missing, and name the restore
     command.

## Consequences
- The working tree loses about 620 MB of M1's raw records. A clone made with
  `git clone --filter=blob:none` downloads them only when `restore` asks for them.
- Every reference to a raw file still resolves: through `restore` for M1, and through `fetch`
  for M2.
- **Uploading M2's archives needs a person**, through the GitHub release page or `gh release
  upload`. The manifest's hash makes a wrong upload detectable.
- M1's numbers and reports do not change. Only where their raw inputs sit changes.
