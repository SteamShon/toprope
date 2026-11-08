# The change check

Link: ① iterate safely. ADR-0009, ADR-0018, ADR-0032 (records), ADR-0033 (the base),
ADR-0013 (incremental). M0a sub-PRs 8 and 9.

`$R` is the `toprope-run` prefix from [`workflow.md`](workflow.md), with `--member authoring`:

```bash
$R check_commit 3-ab12…      # Authoring's action: the kernel's change_check, against the merge base with main
uv run toprope-commits checks DOMAIN 3-ab12…   # the newest record of each check on the commit
```

In code: `Workspace.change_check(commit, since=…, env=…, full=…)`.

It compares a commit with a base and reports what would break or conflict, before anything
is deployed. It exits 1 when a check reports an error. The report is printed, written to
`.toprope/checks/<commit>.json`, and recorded on the commit.

## The checks

| Check | What it reports | Severity |
|---|---|---|
| `structural` | references and types (`validate_domain`) | errors fail; warnings that are new are marked |
| `semantic` | states the small world can no longer reach, actions no matrix cell allows, `undecided` cells | newly lost: error; already so: warning; undecided: info |
| `scenarios` | scenario regression: the base's scenarios and the new ones, run on the new model. A scenario the new version dropped still runs | a failing scenario is an error |
| `harness` | the generated harness at the model level: cells, invariants, gate-tier exploration | any finding is an error |
| `tla` | with a TLC jar (`tlc=`, or `TOPROPE_TLC_JAR` for the kernel), TLC on the model level, its violation replayed (ADR-0043, ADR-0044) | a harness gap, a model mismatch, an error or a reached bound: error |
| `log_replay` | every past action in the domain's event store, re-decided by the new model at its original time: "with this change, 1 past action would have been blocked" | blocked by the new model but not the base: error, or a warning when the object is finished now (no action allowed from its state); blocked by the base too: counted in the note; would now set fields differently: warning |
| `in_flight` | objects in that store whose type or current state the new version lacks (stranded; migration plans come in M0b) | error |
| `capability` | who can reach each outcome (an object's state, or a property an effect sets), before and after: the actions, from which state, by which actors, whether a person is required, and the preconditions on the way (ADR-0048) | a widening of an outcome that existed before: warning (a new path, a new actor, a path that no longer requires a person, a dropped precondition); a narrowing, or a new outcome: info; skipped for a first version |
| `nl` | natural-language conflicts in descriptions and judgment rules, by an `NLChecker` (an LLM adapter) | warnings only; skipped when none is configured |

- **Without a structurally valid declaration**, the checks that need a model do not run.
- **Without an event store**, log replay and the in-flight check do not run: nothing was
  deployed. The kernel uses the domain's own event log when it serves the domain (a self
  domain's `domains/<domain>/events`, kept in git), else its deploy environment's store.
- **A stricter rule does not rewrite finished history.** A past action newly blocked on an
  object that is finished now (its state allows no action) is a warning: nothing in flight
  depends on it. On an object still in flight it is an error. Delivery's probes (#147) made
  past checkbox verifications invalid, on requests already verified.
- **Only what this change newly blocks is an error.** A past action the base model blocks
  too was blocked by an earlier change, already checked and approved; it is counted in the
  note ("2 blocked by the base too"), so it does not fail every later check.
- **Log replay keeps the recorded history.** Each past action is decided against the state
  the recorded events left, so one blocked action does not cascade. A past actor is assumed
  to have held every role the base version allowed for that action, roles named by actor
  rules included; pass `roles_of` (the Identity port) to resolve real roles. Events are
  replayed in time order; events on different objects with the same time keep no known
  order, so a coarse clock can misorder cross-object lookups.
- **The environment must run this domain.** An environment where another domain is deployed
  is not replayed, and a mistyped `--env` is an error, never an empty environment.
- **A base with structural errors is no baseline**: nothing is reported as newly lost
  against it.

## Incremental (ADR-0013)
- **The impact report comes first**, before anything runs: the changed elements and the tests
  and past actions they affect, in domain terms ("changes 1 cell(s); affects 4 cell test(s),
  3 flow(s), exploration; replays past launch_experiment"). It is in the report as `impact`,
  with its time (target ≤ 2 s).
- **Dependencies are static and conservative.** A case test depends on everything about its
  action (the action, params, preconditions; a cell test only its own cell), on every object
  reachable from the action's object through links, on roles, handoffs and fixtures, and on
  the case as the small world built it, and on the world's actor names. Dependencies are
  taken over both versions, so removing an element affects what read it. Flows and
  exploration depend on the whole declaration's shape: interface elements without their
  text, the other elements whole (fixture and scenario data included), never the glossary
  or purpose. A description or glossary change reruns nothing.
- **Results are cached** in `.toprope/cache`, keyed by the hash of a test's inputs and the
  toolchain (the kernel's source). Unchanged tests are not re-run; a damaged entry is a miss.
  `--no-cache` runs everything.
- **Log replay re-decides only affected actions**; the others still advance the replayed
  state.
- **Soundness.** `--full` also runs everything uncached and lists **selection misses**: tests
  that fail uncached but passed from the cache, i.e. bugs in this analysis (target 0; the
  command exits 1 if there are any). It compares with the cache, so it cannot run with
  `--no-cache`. Run it in the background and before release PRs.
- Not yet: the background exploration tier and build taint (ADR-0013 §3).

## The base
By default the base is the commit's merge base with `main` (ADR-0033: a branch is reviewed
from where it left `main`). For a commit already in `main` it is the first parent, and with
nothing approved the commit is checked as a first version, so nothing counts as "newly"
lost. `--since` sets the base explicitly.

## Records on commits (ADR-0032)
Each run appends to `checks.jsonl` in the commit store, in one write: one record per check
(`ok: null` for a check that did not run that time) and `change-check` for the whole
(commit, check, ok, summary, base, at, run). The newest record of
each check is the commit's status (`CommitStore.check_status`). A preview appends
`preview-harness`. Whether approval requires green checks is the Authoring declaration's
decision (ADR-0032 recommends yes).

## From a declaration
The kernel service `change_check` (`domain`, `commit`) runs the same check, uses the domain's
own event log for log replay (or the kernel's deploy environment when it has none), records the result, and returns
`passed`, `errors`, `warnings`, `failing` and `summary`.
