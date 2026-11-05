# The change check

Link: ① iterate safely. ADR-0009, ADR-0018, ADR-0032 (records), ADR-0033 (the base),
ADR-0013 (incremental). M0a sub-PRs 8 and 9.

```bash
uv run toprope-author change-check                    # the `work` head, against its merge base with main
uv run toprope-author change-check 3-ab12… --since 1-cd34… --env .toprope/envs/local
```

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
| `log_replay` | every past action in the environment's event store, re-decided by the new model at its original time: "with this change, 1 past action would have been blocked" | blocked: error; would now set fields differently: warning |
| `in_flight` | objects in that store whose type or current state the new version lacks (stranded; migration plans come in M0b) | error |
| `nl` | natural-language conflicts in descriptions and judgment rules, by an `NLChecker` (an LLM adapter) | warnings only; skipped when none is configured |

- **Without a structurally valid declaration**, the checks that need a model do not run.
- **Without an environment** (`--env`), log replay and the in-flight check do not run:
  nothing was deployed.
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
  the case as the small world built it. Flows and exploration depend on the whole
  declaration without its text, so a description or glossary change reruns nothing.
- **Results are cached** in `.toprope/cache`, keyed by the hash of a test's inputs and the
  toolchain (the kernel's source). Unchanged tests are not re-run; a damaged entry is a miss.
  `--no-cache` runs everything.
- **Log replay re-decides only affected actions**; the others still advance the replayed
  state.
- **Soundness.** `--full` also runs everything uncached and lists **selection misses**: tests
  that fail uncached but passed from the cache, i.e. bugs in this analysis (target 0; the
  command exits 1 if there are any). Run it in the background and before release PRs.
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
The kernel service `change_check` (`domain`, `commit`) runs the same check, uses the kernel's
deploy environment for log replay when it has one, records the result, and returns
`passed`, `errors`, `warnings`, `failing` and `summary`.
