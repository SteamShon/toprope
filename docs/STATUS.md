# Status

Link: none (enabler). A snapshot of what is done and what is left, and nothing else. History
lives in git, the PRs and the ADRs (`git log -- docs/STATUS.md` shows which PR last changed
this page); plans live in [`roadmap.md`](roadmap.md) and the milestone and experiment docs.
Every PR into `develop` or an `umbrella/*` branch fixes any line here it makes untrue, or says
why not; each release trims it ([`AGENTS.md`](../AGENTS.md), "Progress").

Updated: 2026-11-07 · Cleaned for release: `v0.1.0`

Legend: ✅ done · 🟡 in part · ⬜ not started

## Summary

| Milestone | Link | Status | Note |
|---|---|---|---|
| M0a thin slice | none (enabler) | ✅ | released as `v0.1.0` (#65); the tag is not pushed yet |
| M1 self-compile | ① ⑥ pilot, no verdict | 🟡 | Phase A and the switch-over done; instruments and Phase B left |
| M0b surfaces and effects | none (enabler) | ⬜ | |
| M2 dogfood | ① ② ③ | ⬜ | the first ① and ② verdicts |
| M3 shared language | ④ | ⬜ | |
| M4 evolution | ⑤ | ⬜ | |
| M5 handoff and release | ⑥ (partial) | ⬜ | |

No link has a verdict yet: every row of the README
[claim-status table](../README.md#claim-status) is `untested`.

## M0a thin slice

✅ Released in #65 (umbrella #15): declarations and semantics, model interpreter, Execution and
event stores, `toprope-server` MCP, authoring MCP, world map, harness, change check with log
replay and in-flight check, incremental analysis, commits and branches (ADR-0029, ADR-0033).

## M1 self-compile

| Item | Status | PR |
|---|---|---|
| Probe suite (P01–P08) and verdict rules, frozen (`experiments/m1/instruments/FROZEN.json`) | ✅ | #56–#58, #61 |
| Change requests (20) and the sealed change key (options drafted on request and selected by the researcher, ADR-0034), frozen | ✅ | #92 |
| Binding (intent → element names; drafted on request, ADR-0038), frozen | ✅ | #93, #94 |
| Phase B run protocol (drafted on request, decided by the researcher), frozen | ✅ | #123, #133 |
| Phase A: the Authoring and Delivery self domains, built and confirmed | ✅ | #69, #73, #74 |
| First self-domain commits approved | ✅ | #77 |
| Domain guide at preview | ✅ | #67 |
| Mechanical harness layer (ADR-0035) | ✅ | #71 |
| Domain commit store kept in git | ✅ | #75 |
| Generated `toprope-run` and how-to-work guide (ADR-0036) | ✅ | #76 |
| Switch-over (ADR-0037, umbrella #81): only the kernel stays hand-built | ✅ | #81 |
| Phase B: the change sequence on the three arms | ⬜ | |
| M1 report ([`experiments/M1-self-compile.md`](experiments/M1-self-compile.md)) | ⬜ | |

### Switch-over (umbrella #81)

| Sub-PR | Status | PR |
|---|---|---|
| 1. Workspace into the kernel; interview operations as kernel services | ✅ | #80 |
| 2. Per-domain layout and a JSONL event store in git; Authoring calls the interview services | ✅ | #82, #83 |
| 3. `toprope-run` as yourself from your git identity (`toprope.identity.yaml`) | ✅ | #85 |
| 4. The whole loop on the generated tools, end to end; the regeneration check passes | ✅ | #86 |
| 5. Remove `toprope-author`, `toprope-deploy` and their hand-written guides; merge, checkout and confirm-all declared; the kernel's command reference generated (`docs/kernel-commands.md`) | ✅ | #89 |
| Researcher sign-off; the umbrella merges into `develop` | ✅ | #81 |

Signed off by the researcher and merged into `develop` (#81). Nothing but the kernel is
hand-built: the self domains run from their declarations, and their guides and the kernel's
command reference are generated.

### How the self domains run

- `toprope-run --composition domains/toprope-self.composition.yaml --member <m>` runs the whole
  loop (commands in [`workflow.md`](workflow.md)). Each member's events go to its own
  append-only log, `domains/<domain>/events/`, kept in git; example objects never go into it.
- You are your git email, looked up in `toprope.identity.yaml`. An agent on your machine has
  your git email too; an `agents` entry applies only to an agent with its own email. Actions
  that require a person also ask on your terminal: a guard against mistakes, not a boundary.
- `toprope-run` reports what a command set off (`then`): each kernel call, its reply, the
  object a creating reply made (for example the new commit's id), and each handoff.
- From a cloud session, the researcher's own steps (freeze, confirm, approve, deploy) are
  committed as a human request and run after the researcher approves the run in GitHub
  (ADR-0039, #95); first used for real in #96 (both self-domain Drafts opened, recorded as
  the researcher, the approval run in the commit).
- Approving a change is `commit_draft`, `check_commit`, `approve_commit` (there is no `ship`
  shortcut any more); `confirm_all_proposed` confirms every proposed element at once. Reads
  are `toprope-commits` (branches, log, diff, checks, deployed).

## Lessons from pstack (umbrella #121, link: ① ② ③ and none)

Six changes taken from a review of the pstack agent skills (`cursor/plugins`), one sub-PR
each into `umbrella/pstack-lessons`. Each sub-PR changes only its own item below.

- ✅ 1. Rules enforced by checks, not text: a `checks` workflow runs the tests and
  `instruments.py verify --run`; a workspace source that matches no file is reported
  (`Workspace.stale_sources`, the mistake #91 fixed); `AGENTS.md` pairs each rule with what
  enforces it. Three rules stay text only (gold sets, real tests, model identifiers): no past
  mistake to prove a check on (#122)

- ✅ 2. M1 Phase B run protocol (`experiments/m1/instruments/run-protocol.md`): blinding, grading
  by sanitized label, reviewers 5 runs and probes 3, the spread with every number, run records
  in git. Drafted (#123); its four questions decided by the researcher on 2026-11-07, and frozen
  by hash (`freeze-protocol`; `verify --run` needs it) (#133)

- ✅ 3. Commits cite evidence that must resolve, with how strong it is (ADR-0041, Resolved 3, with
  a dated note). The kernel's `cite_evidence` refuses a ref that does not resolve (an interview
  line, a source chunk, a check recorded on the commit, a stored event, or an approval run the
  `human-request` workflow recorded in `.toprope/approval-runs.jsonl`) and records its strength
  (pointed, ran, observed or approved); `toprope-commits evidence` lists it. One mechanism: the
  `commit` service no longer takes free-string evidence. Authoring calls `cite_evidence` and
  `commit_draft` dropped `evidence`, through the loop from develop's `main`: proposed by the
  agent, confirmed, approved, deployed and verified by the researcher (Authoring `main` is
  `7-92bcb1c921be21bd`) (#124)

- ✅ 4. World map state charts show where the harness found a break: failed arrows, `breaks`,
  `mayBreak` and `unreachable` states, arrow conditions in brackets, and each minimal flow told
  step by step (`minimal-flows.md`; `docs/world-map.md`). A TLA+ export checked by TLC, as a
  second oracle beside bounded exploration: ADR-0043, umbrella #135 (#125)

- ✅ 5. Harness mutants (`toprope-harness --mutants`, `docs/harness.md`): each seeded break given to
  the execution level must be caught. Three survived in the examples (paid-media's `step-limit`
  and `not-the-proposer`, refunds' `within-window`), so precondition tests now make a boundary
  instance when the world has none, including for preconditions that read `params`. Every
  mutant of the examples and both self domains is caught (Authoring 61, Delivery 29) (#126)

- ✅ 6. The self domains' logs advance on one line: `AGENTS.md` says two branches never run the
  loop at the same time, and the `checks` workflow fails a PR whose head does not extend each of
  the base's append-only logs (`tools/logs_check.py`; it catches #124's first, diverged run)
  (#129)

## TLA+ cross-check (umbrella #135, link: ③)

The harness checks a declaration by bounded exploration. ADR-0043 adds a second, exhaustive
oracle: the declaration exported to TLA+ and model-checked by TLC in CI, each counterexample
replayed on the interpreter. One sub-PR each into `umbrella/tla-cross-check`; each changes
only its own item below.

- ✅ 1. ADR-0043 (accepted): one declaration's model level; TLC in a pinned `tla` CI job; each
  counterexample replayed on the interpreter, a harness gap or a model mismatch fails; actions
  using time, links or creation left out and reported; every example and both self domains under
  a 1,000,000-state bound (#136)

- ✅ 2. Exporter (`toprope.tla`; `toprope-harness --tla DIR`): a declaration's model level as a
  TLA+ module and TLC config, values tagged so the check language stays fail closed; actions that
  create objects, use time or follow links are left out and named (#137)

- ✅ 3. A `tla` CI job (`.github/workflows/tla.yml`, `tools/tla_check.py`): TLC 1.8.0 pinned by
  sha256. The four examples are checked (paid-media 133,686 states, no break), and a seeded break
  (paid-media without `not-a-holdout`) must be found, so the job can fail; a model TLC cannot
  check, or a reached state bound, fails (#137)

- ✅ 4. Replay (`toprope.tla.replay`): each TLC counterexample is read from TLC's trace and taken
  again on the model level; a break the harness also reports is `known`, one it missed a `harness
  gap`, one the interpreter does not reproduce a `model mismatch`; the last two fail the `tla` job,
  and the seeded break must be found and reproduced (#138)

- ✅ 5. Every example and both self domains in the `tla` job, each fixture checked alone (the
  modeled instances are independent). TLC first found a **harness gap** in each self domain (a
  late kernel reply with a failing result on an approved commit, or on a deployed request); both
  declarations now refuse those replies (item 6), and the harness finds the one-step kind itself
  (item 7) (#139)

- ✅ 6. The self domains refuse the late kernel replies TLC found: Authoring's `record_check` on an
  approved commit (`settled`), and Delivery's `preview` of a deployed request (`not-deployed`; a
  refused deploy can still be retried). Through the loop: proposed by the agent, confirmed,
  approved, deployed and verified by the researcher (Authoring `main` `9-b4ec65433222f096`,
  Delivery `main` `4-3e90586c40faf7d7`) (#140)

- ✅ 7. Param tests: each allowed cell, on every instance in its state, with one finite param (boolean,
  enum, integer) set to each other value; the harness now finds the Authoring break by itself.
  A break that first needs a state the small world never builds (Delivery's) stays TLC's;
  `docs/harness.md`, "What each one catches" (#141)

## Review follow-ups (umbrella #143, link: ① ③)

From an integrated review of #135 (2026-11-07): the mechanical guarantee had gaps the self-compile
showed, and the loop is heavy even for experts. One sub-PR each into `umbrella/review-follow-ups`;
each changes only its own item below. Not here: a confirmation view for non-developers (needs
M0b's UI), checking the non-developer claim (M1 Phase B, M2), TLC modeling creation and links
(Next).

- ✅ 1. A late kernel reply is recorded, not applied (#148)
  Narrowed from "only for a call that is waiting for it": the review's gaps were late replies.
  A reply whose object someone other than the kernel moved out of its called-in state is
  refused with `late-reply`, its result kept in the outbox record.

- ✅ 2. The change check replays past actions from the domain's own event log in git (#144)
  `toprope-run`/`toprope-server` with `--composition` give the kernel each member's store, so
  `change_check` replays a self domain's real history with nothing deployed. Only actions this
  change newly blocks are errors; the base's own blocks are counted. On Authoring's log: 96 of 96
  re-decided, 0 blocked, 2 blocked by the base too (the `commit_draft` calls with `evidence`
  from before #124).

- ✅ 3. Breaks that need several steps are caught before approval, not only in CI (#145, ADR-0044)
  With `TOPROPE_TLC_JAR`, the change check runs TLC (`tla` check) and the kernel approves only a
  commit whose `tla` check passed. The human-request workflow installs the pinned TLC; a request
  runs `check_commit` before `approve_commit`.

- ✅ 4. One change, one request: confirm, commit, check and approve in one declared step (#146)
  A request step's target may be `$commit`: the commit an earlier `commit_draft` step of the same
  request made, read from its output. `human_request.py change` writes the four steps. A request
  is tooling, not a declared action: the steps stay the Authoring declaration's own.

- ✅ 5. `verify` runs the domain's probes instead of taking a checkbox (#147)
  The kernel's `probe` service checks a deployed commit in use: its build and the floor, its
  scenarios at the execution level, and every object in the deployed store against every
  invariant (`check.in_use`); recorded as the `probes` check. Delivery's change is proposed
  (`run_probes`, `record_probes`, `verify` needs `probes-passed`, a new deploy clears probes);
  The researcher confirmed, approved, deployed and verified it in one human request (approval run
  42349530977): Delivery main `5-35b215f4a8901224`, its `tla` check passed in the approval
  (ADR-0044, 8492 states), its probes passed.
  A proposal inside an element (`actions.verify.effects`) now proposes the element again.
  The first approval run stopped at the change check: log replay found the four past checkbox
  verifications blocked. They are on finished requests, so they are now warnings (the
  researcher's choice); a block on an object in flight stays an error.

- ✅ Integrated review of the umbrella (#149)
  Two gaps, fixed: the probes read the deploy environment's store, which is fresh in every
  approval run, so for the self domains they checked no object in use; and a new invariant that
  objects in use already break went unreported (Delivery's four verified requests from before
  the probes). The probes now read the domain's own log when the kernel has it, and the change
  check's `in_flight` tests every object in use against the new invariants: an object in flight
  that breaks one is an error, a finished one a warning, as in log replay.

## The self domains run their deployed commit (#150, ADR-0045, link: ③ ①)

From the integrated review of #143. A deploy is recorded with the commits
(`.toprope/commits/<domain>/deployments.jsonl`, in git). With `--kernel-root`, `toprope-run` and
`toprope-server --composition` run each member's deployed commit, else its approved `main`, so
a working-copy edit changes nothing that runs until it is deployed, and events carry the
commit's sequence number as `domain_version`. `--working-copy` runs the files.

## A creating action sets every required property (#151)

A review leftover from #86. The validator warns (`unset-on-create`) when a create action leaves a
required property to an optional param or to nothing. It is a warning, not an error, so a
declaration already running with it can still be fixed through the loop. It found one:
Authoring's `add_source` leaves `Source.local_only` unset when the param is left out. The fix,
`local_only` optional (absent means not local-only, as the source spec reads it), was confirmed,
approved, deployed and verified by the researcher (approval run 42363055975): Authoring
`10-01b4e6464862bbf9`, its `tla` check passed in the approval (219312 states). It is the first
deploy recorded with the commits (ADR-0045): the events after it carry `domain_version` 10.

## The kernel's server reads sources (#154)

Formerly Next 3, before M2. With `--kernel-root` and `--workspace`, `toprope-server` has a
`read_source` tool: a source's chunks, redacted, each with its ref; a local-only source is
refused; a read, not an action, so what it serves goes into the workspace's usage log, never into
an event log.

## TLC models creation (#155, ADR-0043 follow-up, link: ③)

Creating actions are steps of the exported model: one fresh id per created type, the empty world
as one more start, a creating step only from it. A creating param no expression reads gets one
value. Actions for `system` (a handoff) run as that actor. The self domains now leave out only
Authoring's `elements-cite-a-source` (a link path). A second seeded break, made by creation alone,
must be found by the `tla` job.

## TLC models link paths (#156, ADR-0043 follow-up, link: ③)

A link path reads the linked objects from their fixtures, a constant: the linked object or null
(a list for a link to many). It may read only what no modeled action changes (whether the object
exists, fields no action sets), so the instances stay independent. Nothing of the self domains
is left out now. A third seeded break, read through a link (an Element citing no Source), must be
found by the `tla` job.

## TLC models time (#PR, ADR-0043 follow-up, link: ③)

Time is the harness's clock, frozen, as in replay: `now()` is that instant, an effect stores it
as its ISO string, and every ISO time the model can hold has its offset and whole days in two
tables, for comparisons and `days_since`. A fourth seeded break, through `days_since`, must be
found by the `tla` job.

## M0b, M2 to M5

Not started. Plans: [`roadmap.md`](roadmap.md).

## Next

1. M1 Phase B: the change sequence on the three arms (every M1 instrument is frozen; the
   harness runs `instruments.py verify --run` before each arm run), then the M1 report.
2. Push the `v0.1.0` tag on `main` (maintainer); release M1 to `main`.
3. When a domain is shared by several people or agents (M2, or a hosted server): its event
   log moves from git to a database (`--store postgres:DSN` for a composition, one schema per
   member), through a new ADR superseding decision 29A for that case; an export to git can
   keep the audit trail (decided 2026-11-06). Until then the self domains keep their logs in
   git (`domains/<domain>/events/`).
4. ADR-0041's follow-up work (decided 2026-11-06), the third on in
   `umbrella/adr-0041-follow-ups` (#114). Done: approval refuses commits with proposed
   elements, and the change check records how many are left (#110); every decision action takes
   an optional `rationale` (#111); a check can read `actor.principal` (#113);
   `examples/paid-media/` shows the exception pattern (#115); every event records the
   permissions it ran under (#116); a commit may cite its evidence (#117, #118: free strings
   on `commit`, Authoring commit `5-c8fd1b8fc98be17c`), replaced by typed evidence that must
   resolve, cited with `cite_evidence` (#124, in the pstack umbrella).
5. ADR-0042's follow-up work (accepted 2026-11-07): done: `domain_version` with the deployment
   log gives the rule in force when an event was decided, documented, the self domains too
   (ADR-0045, #150); read visibility defined in the schema (`read`, refused
   until M0b); in M0b, deadlines with timers, read visibility enforced by the query and MCP
   read tools, an observed time on facts from adapters, identity mappings on adapters; in M2,
   `confirmed_at` and `review_by` warnings; in the M4 spec, goals, expected outcomes and the
   outcome-to-decision link.
6. ADR-0043's follow-ups: make `tla` a required check on `develop` (maintainer). Creation
   (#155), link paths to what no action changes (#156) and time, frozen at the harness's clock
   (#PR), are modeled; no declaration in the repository leaves anything out.

## Left from reviews

Each item names the PR it came from and the review date. The PR that resolves an item deletes
it; each release's cleanup PR handles items older than one release.

- Nothing keeps the author of a commit from approving it: `approve_commit` checks only that a
  person approves (`requires: human`) a commit whose checks passed. Charter §5 says "no
  self-approval"; ADR-0032 keeps one approver in M1. Decide whether to enforce author ≠
  approver before M2, when a domain gets more than one owner (#102, 2026-11-06)
- `propose_element` on a path that is not an element (for example `glossary.<term>`,
  `scenarios.<id>`, `world.fixtures`) writes the value without provenance instead of failing, so
  such a change shows only in the commit's review diff; #147's Delivery change has three
  (#86, 2026-11-06; again in #147, 2026-11-07)
- `toprope-run` reads `git config` twice per command (once to check the caller, once in
  `submit`) (#85, 2026-11-06)
- `identity/git.py` repeats the git lookup in `Workspace.identity`, and the two name a person
  differently (the identity file's name vs git `user.name`); only the workspace API's
  `confirm(via="cli")` still uses the latter (#85, 2026-11-06)
- The `human-request` workflow pushes its result with the workflow token, so no `pull_request`
  check runs on that head, and the ruleset does not accept the `status` run the workflow
  dispatches; the PR needs one more commit before it can merge. A push token that triggers
  workflows (a GitHub App or a fine-grained token, set up by the maintainer) would remove the
  step (#96, 2026-11-06)
- `merge_main` writes the working copy and records the merge in progress in two steps; a
  commit from another process between them gets one parent, and the next commit a stale
  second one (#89, 2026-11-06)
- The kernel reference generator reads private `argparse` attributes (`_actions`,
  `_SubParsersAction`); a Python release that renames them breaks it (#89, 2026-11-06)
- `Workspace.confirm` and `approve_commit` still name the removed channels (`cli`,
  `elicitation`) (#89, 2026-11-06)

## Open questions

- The README now calls brownfield the case Toprope designs for, but the first brownfield adapter
  is planned for M0b, after M1, and M2 does not require one. Make brownfield an actual priority
  (move the adapter earlier, or a brownfield M2)? That would need an ADR changing the roadmap
  order (#102)
- An agent on the researcher's own machine runs with the researcher's git email, so it acts as
  the researcher for every action that does not require a person. Accept this for M1 (the
  decision 30A trust model), or give local agents their own identity? (#85)
