# Status

Link: none (enabler). A snapshot of what is done and what is left, and nothing else. History
lives in git, the PRs and the ADRs (`git log -- docs/STATUS.md` shows which PR last changed
this page); plans live in [`roadmap.md`](roadmap.md) and the milestone and experiment docs.
Every PR into `develop` or an `umbrella/*` branch fixes any line here it makes untrue, or says
why not; each release trims it ([`AGENTS.md`](../AGENTS.md), "Progress").

Updated: 2026-11-11 · Cleaned for release: `v0.1.0`

Legend: ✅ done · 🟡 in part · ⬜ not started

## Summary

| Milestone | Link | Status | Note |
|---|---|---|---|
| M0a thin slice | none (enabler) | ✅ | released as `v0.1.0` (#65); the tag is not pushed yet |
| M1 self-compile | ① ⑥ pilot, no verdict | ✅ | closed after the recheck ([`M1-report.md`](experiments/M1-report.md)): Toprope with its LLM review leads on recall (first run 0.84 against 0.64 NL; recheck 0.94–1.0 against 0.44–0.62, biased and a reference only); the grader's noise (0.18) moves to M2's grader redesign; six probes carried to M2's probe design; ⑥ inconclusive |
| U usability before M2 (ADR-0049) | none (enabler) | 🟡 | F1 baseline recorded; F2's script written, its run waits for an operator; theme 1 started |
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
| Phase B: the change sequence on the three arms (umbrella `umbrella/m1-phase-b`) | ✅ | #99 |
| M1 report ([`experiments/M1-report.md`](experiments/M1-report.md)) | ✅ | |

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

### Phase B (umbrella `umbrella/m1-phase-b`)

| Sub-PR | Status | PR |
|---|---|---|
| 1. Execution protocol (ADR-0040); amended in 2a to run on the researcher's own Claude Code, on their machine | ✅ | #98 |
| 2a. Harness core: each role a fresh `claude -p` with only the harness's confined tools; stop at the usage limit and resume; progress line; the NL and structured-spec arms; the NL skill's rendering. Tested with a fake model and a fake `claude` | ✅ | #100 |
| 2b. The Toprope arm: a sandbox with fixed tools, the compiler's checks and a preview, the stand-in for person-only steps and its override of a failed check (the floors still hold). Tested on the real kernel | ✅ | #101 |
| 2c. The probes: eight starting states built once per run with the approved tools (a small `library` domain), the same generic tools in every arm, the deployed domains' generated MCP in the Toprope arm; the probe agent never sees what a probe checks | ✅ | #103 |
| 3. The three arms' materials (`experiments/m1/arms/`): structured and Toprope built from the approved commits, the NL skill rendered blind; reviewed side by side by the researcher | ✅ | #105, #163, #166 |
| 4. Scorer (`grade` proposes labels with a grader, `score` computes the metrics and pilot verdicts from the researcher's confirmed labels; the key opens only here and only after every arm ran every change), tested with a synthetic key; the probes now also run once before any change | ✅ | #106, #164 |
| 5. Dry run (changes 1–2), run by the researcher: time and usage per change | ✅ | #109 |
| 6. Full run, scoring confirmed by the researcher, M1 report. The first full run (#112) is superseded (`experiments/m1/runs/superseded/`): it ran before the run protocol was frozen, and from `authoring@4` | ✅ | #112, #166, #170 |
| 7. Re-baseline on `authoring@9` + `delivery@1` (researcher's decision, 2026-11-07): today's harness finds an invariant break in `authoring@4`, so the deploy floor refuses it. The harness reads the baseline from fixed repository revisions, never the working tree; materials rebuilt; the binding's `domain_version` amended; the NL skill removed until the researcher renders it again (the NL arm refuses a stale one); the editor is told when the kernel refuses its proposal | ✅ | #163 |
| 8a. No experiment words (protocol §1): the harness's prompts, the change requests and probe requests as given, tool names and descriptions, and workspace file names are checked, and a run stops before showing one; tools never show the workspace's absolute path. The decision log (§4): `runs/phase-b-runs.tsv`, append-only, one row per edit, review or check, deploy and probe, with a pointer to its evidence; a change run again is superseded by a new row | ✅ | #164 |
| 8b. Repeats and spread (protocol §2–3): five reviews and three probe runs per change; the Toprope arm's checks once, again uncached on three changes, and five timed repeats with the part that bounds each; every arm's flags graded in one pass per change under random labels A, B, C (the mapping kept apart), the script's and the grader's labels both kept; recall and precision per run with mean, minimum and maximum; the noise floor, marked next to the rule a gap affects. The agents' prompts are frozen with the protocol (§1): their hash goes in `FROZEN.json` through `python -m phase_b freeze-prompts` (the researcher's step; a change needs `--reason` and keeps the old hash), and a run refuses until then | ✅ | #164 |
| 9. How Phase B runs now (ADR-0047, superseding ADR-0040 §2): a Remote Control session on the researcher's computer runs the harness from `phase_b/RUNBOOK.md`, never opening the key, the binding or the blind labels; the researcher keeps three judgments; `to-decide` lists only the grades that need one | ✅ | #165 |
| 10. What an older run leaves behind is not a run: `worlds/` counts as built only when every probe's starting state is in it, and a Toprope sandbox only once the materials are; caches git ignores (left by `git mv` of the first run) are kept aside, and the harness builds afresh. Found by the first dry run on the researcher's computer (2026-11-08), which stopped at once on all three arms | ✅ | #167 |
| 11. The Toprope arm's tools stay fixed: its stand-in and editor run the toolchain's files (`--working-copy`). Since ADR-0045 a member runs its deployed commit, and the sandbox's commit stores are the arm's, so the arm's own deployed changes had become its tools; change 9 (a request field the handoff does not send) then left the composition unable to compile and stopped the arm at change 10 (2026-11-08). The Toprope arm's changes 1–9 ran on drifting tools and run again | ✅ | #168 |
| 12. The run's first two steps (RUNBOOK 1–2): the agents' prompts frozen at the researcher's instruction (2026-11-08); the NL skill rendered again from `authoring@9` + `delivery@1` and accepted by the researcher side by side with the declarations (2026-11-08) | ✅ | #166 |
| 13. The run (RUNBOOK 3–6): dry run, full run (20 of 20 on each arm), grades confirmed by the researcher (the three probe runs `to-decide` listed, 2026-11-08), score (`runs/phase-b/scoring/metrics.json`) | ✅ | #166 |
| 14. The Toprope arm's flags on the kernel's inputs: the first scored run (#166) took them by checking each commit again on the deploy environment's events, which are empty, so every log replay finding was lost (the kernel's own check replays the member's history, ADR-0045). Flags now come from the recorded base and the member's own history, and each says whether its base had it (`carried`); `phase_b recheck-toprope` takes them again from the stored commits (nothing is run by a model), keeping the first under `check.original`; then `grade` and `score` run again | ✅ | #169, #170 |
| 15. The Toprope arm with its LLM review (the researcher: the fair comparison is Toprope's declarations, scenarios, compiler and LLM together against the NL skill with an LLM, 2026-11-08): `phase_b combine-toprope` reviews the Toprope arm's own edits five times with the frozen review prompt and adds the compiler's flags, into `runs/phase-b-combined` for `grade` and `score`; an arm added after the first scoring, reported as such. Also a secondary precision that counts a compiler check once per change and leaves out what the base had | ✅ | #172, #173 |
| 16. The grader is asked once more for JSON when it answers in prose (M1 lost six verdicts that way, decided by the researcher); a gap equal to the noise floor is not "within" it (both rounded) | 🟡 | |

How a run works (ADR-0047): the researcher opens a session through Remote Control on the
repository's folder on their computer, and it follows [`phase_b/RUNBOOK.md`](../experiments/m1/phase_b/RUNBOOK.md):
it runs the harness, pushes the results and stops for the researcher's three judgments (the
prompts, the NL skill, the grades `to-decide` lists). Each role is still a fresh, tool-confined
`claude -p` the harness starts; a stopped run continues with the same command.

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

## TLC models time (#157, ADR-0043 follow-up, link: ③)

Time is the harness's clock, frozen, as in replay: `now()` is that instant, an effect stores it
as its ISO string, and every ISO time the model can hold has its offset and whole days in two
tables, for comparisons and `days_since`. A fourth seeded break, through `days_since`, must be
found by the `tla` job.

## Scenarios are elements (#161)

A review leftover (#86, #147), as the researcher chose: a scenario carries `source` and
`status` like an action, so an agent's scenario is proposed until a person confirms it, and
approval counts it. Fixtures and the glossary carry no provenance: proposing them writes an
`unmarked-proposal` line to the interview log, and the change shows in the commit's review diff.

## The author does not approve, where a domain says so (#162, ADR-0046)

A review leftover (#102), as the researcher chose: `approval: {distinct_from_author: true}` in a
declaration makes the commit store refuse an approval by the commit's author, with the rule read
from `main`. Off by default, and off for the self domains in M1 (one owner); turn it on with a
second owner.

## M1's findings, before M2 (umbrella `umbrella/m1-findings`, link: ① ③)

From [`M1-report.md`](experiments/M1-report.md), *What M2 takes from this*.

| Item | Status | PR |
|---|---|---|
| ADR-0048: outcome rules, and a capability diff in the change check | ✅ | #176 |
| The capability diff (a check over two declarations; no schema change): the change check's `capability` | ✅ | #177 |
| Outcome rules: schema, validator, interpreter, harness, TLA+ export (`requires: human` or roles; the generated guide and the self domains' adoption follow, in the M1 recheck) | ✅ | #179 |
| Grouped findings in the change report (`groups`: one per check, severity and message, with a count) | ✅ | #180 |
| The natural-language check: `CommandChecker` (`TOPROPE_NL_COMMAND`) gives an LLM the changed elements, the capability diff, the rules and the declaration (ADR-0009) | ✅ | #181 |
| An editor that proposes a patch: the Toprope arm's editor gets `propose_patch` (several elements, in order, stopping at the first refused) and `check_draft` (the draft validated before a commit) | ✅ | #182 |
| Probes that pass before any change: why they fail at `seq: 0` ([`probe-baseline-findings.md`](../experiments/m1/probe-baseline-findings.md)): criteria the right behaviour fails (P05, P07), unequal worlds (the Toprope agent's grant lacks `deliver`/`deploy`), strict readings; adopted by the researcher, in the M1 recheck | ✅ | #183 |
| M2's design, a draft for the researcher ([`M2-design.md`](experiments/M2-design.md)): the full Toprope check against a structured spec reviewed by an LLM, the same edit checked both ways, grouped precision, the grader's noise, probes gated before any change, draft verdict rules | ✅ | #184 |

## M1 recheck (umbrella `umbrella/m1-recheck`, link: ① ⑥)

Preregistered in [`M1-recheck.md`](experiments/M1-recheck.md): the improved Toprope rerun on M1's
change list, to close M1 before M2. Reference numbers only (ADR-0048 §6); M1 closes on the probe
gate, a clean pipeline and the grader's measured noise.

| Item | Status | PR |
|---|---|---|
| Preregistration: what changes, what stays, the exit criteria | ✅ | #187 |
| #179's leftovers: the `check` form of `requires` (validator, interpreter, harness, TLA+ guard; the schema generated with rules), `rule-agent:` harness cases with an agent for the role's person, rules in the generated guide, the invariants stage asks for rules | ✅ | |
| Mechanical promotion (`python -m toprope.decl.rules suggest`: an outcome every non-system action reaches only with `requires: human` gets that rule; the self domains get 5 and 5, and pass their checks with them); the Phase B log keeps one header under a lock and `phase_b status` leaves out runs moved aside | ✅ | |
| Authoring's `record_questions` keeps the bundle's questions: `stage_questions` also returns them as one string (`text`), and `Draft.questions` holds it; proposed in the loop with the rules; approved in `authoring@11-4961f900bb4663e1` | ✅ | #192 |
| The probes: each probe agent's grant adds what its task asks (`TASK_ACTIONS`; a person-only action stays refused); the gate in the scorer (`probe_gate`; `found_after_deploy_ungated` kept); the grader reads a probe's `examples`; the amended suite (P05, P07 judged on what the agent did and what its tools show; examples for P01, P04, P08), amended by the researcher's approved request (`FROZEN.json`, version 2) | ✅ | #191 |
| The grader's second sitting (`grade --into scoring-2`) and its noise (`compare-gradings`, `grader-noise.json`); the recheck's steps in the RUNBOOK | ✅ | #198 |
| Criterion 3 met by measuring the grader's noise (0.18 of recall, over the 0.1 limit; amended again 2026-11-10): nobody adjudicates; `score` reports each arm's recall and precision from both sittings with their range (`by_sitting`); the adjudication commands (#217, #227) removed | ✅ | |
| The self domains adopt the promoted rules (Authoring 5, Delivery 5): confirmed, approved, deployed and verified as `authoring@11-4961f900bb4663e1` and `delivery@6-c2678fc294429d48` (approval run 42605372607; three runs before it found and fixed TLC's state space, #195, and unseen proposed rules, #199) | ✅ | #192 |
| No experiment words in what an arm sees: `Draft.questions` and `record_questions` cited the recheck's own doc (`docs/experiments/M1-recheck.md`), which the arms' materials would show; re-cited to ADR-0025 and ADR-0037 through the loop, approved as `authoring@12-acf2a5f6e362166c` | ✅ | #205 |
| The baseline moves to `authoring@12-acf2a5f6e362166c` and `delivery@6-c2678fc294429d48` (`phase_b/baseline.py`); the structured and Toprope arms' materials rebuilt; the NL skill removed, to be rendered again | ✅ | |
| Harness fixes found closing the recheck: the script no longer scripts capability or info findings as `seeded` (their `where` is the edited element by construction; 67 and 70 flags in the two sittings), `rescript` takes those labels back from graded sittings (an unlabelled repeat takes the grader's label of the same finding); `to-decide` stops asking about a disagreement marked `decided`; `regrade-missing` grades once more a probe run left without a grade; the probes before any change record their tokens; an end-to-end test runs the recheck's closing steps | ✅ | |
| Every Toprope probe of the recheck ran without its domain servers' tools (they did not connect; nothing stopped it): a conversation whose servers gave no tool now stops as an error, with their status and stderr; servers get longer to connect (`MCP_TIMEOUT`); `check-probe-tools` checks them; `arm --redo-baseline-probes` and `regrade-missing --redo` run and grade the probes before any change again. Toprope's found-after-deploy is not measured in the recheck | ✅ | |
| Phase B rerun (local session, RUNBOOK's recheck section): the NL skill rendered from authoring@12 and delivery@6, accepted by the researcher; three arms and the combined arm run, graded twice, script labels taken back (`rescript`) and one probe run graded again (`regrade-missing`); confirmed and scored. Criterion 3: the two sittings differ by up to 0.18 of recall (limit 0.1), measured; Toprope's probes before any change run again with the domain servers connected (#234, #243, #245) and graded again; criterion 1: P01, P02, P04, P06, P07 and P08 fail the probe gate | 🟡 | #212 |
| The recheck report ([`M1-report.md`](experiments/M1-report.md), *The recheck*): criterion 1 met by its rule (P03, P05 pass the gate; six probes carried to M2 with their causes), 2 met (faults fixed and recorded; #96 dropped: no push token in this public repository, the researcher's decision), 3 met by measuring the noise (0.18, over the limit); M1 closed | ✅ | |

## Usability before M2 (ADR-0049, link: none)

Four umbrellas after a baseline. A sub-PR that runs the self domains' loop waits until no other
open PR changes their commit store or logs (`umbrella/m1-recheck` has them now).

F1 baseline (2026-11-09, `uv run python tools/usability_baseline.py`; the self domains' logs as
of M1, from 2026-11-06 05:12, when the command log begins): per change approved in that window (6),
18.8 commands by a person or an agent, 8.3 of them by a person; 6 approved human requests; 1
refusal and 5 failed effects in 113 commands by a person or an agent (0.053); 1 commit with a
failed check. The logs do not see commands that fail before the gate, so that rate is low; once
theme 1 records those (D1), it is measured again before it is compared (ADR-0049, 5).

| Item | Status | PR |
|---|---|---|
| ADR-0049: the program, its order and targets | ✅ | #196 |
| Baseline F1: friction in the change loop, from the logs (`tools/usability_baseline.py`) | ✅ | #197 |
| Baseline F2: time to a first enforced rule. The script is written ([`U-f2-first-rule.md`](experiments/U-f2-first-rule.md)); the run needs an operator who has not used Toprope (the researcher finds one) | 🟡 | #200 |
| Theme 1, the change loop: B4 citations from a query, C1 `toprope change`, C3 `toprope.yaml`, B5 one diff to confirm, D1 a fix in every error, C2 approvals by risk (its own ADR first) | ⬜ | |
| Theme 2, getting started: A4 `init` and `try`, A3 templates, E1 docs, E2 a tutorial | ⬜ | |
| Theme 3, interview and feedback: B1 choice questions, B2 examples first, B3 a live map, D2 impact as decisions, D3 counterexamples as stories | ⬜ | |
| Theme 4, import and wrap: A1 from `AGENTS.md`, skills, OpenAPI, enums, tickets; A2 an MCP proxy (its own ADR first) | ⬜ | |

## M2's grader (umbrella `umbrella/m2-grader`, link: ① ②)

As decided in [`M2-grader.md`](experiments/M2-grader.md) (2026-11-10): the grader steady enough before
M2 runs, with no person adjudicating grades after the results.

| Item | Status | PR |
|---|---|---|
| The checklist grader: `grade --grader checklist`, four yes/no items per distinct flag (rule B in item `outcome`), each answered k=3 times and decided by majority, the label by a fixed rule; `compare-gradings --first --second --limit` | ✅ | #248 |
| The validation run on M1's combined run: two checklist sittings, noise within 0.05 (local session). First run: the sittings differ by up to 0.1 of recall (nl 0.1, structured 0.08, toprope 0.06), over the limit; the grader is revised and checked again (at most twice) | 🟡 | #252 |
| Rule B's invented examples reviewed and accepted by the researcher (2026-11-10) | ✅ | |
| Revision 1 of the grader (1 of 2): each of the k answers in its own random order, an incomplete answer asked once more, `grade --changes-only` for the check; then the validation run again (local session): the sittings differ by up to 0.02 of recall (nl 0.02, structured 0, toprope 0), within 0.05 | ✅ | #253, #257 |
| The grader frozen with M2's instruments, after the validation run | ⬜ | |
| Validity, not only consistency: the grader's agreement with the domain expert's own labels on a sample of M2's pilot flags, and which model grades (proposed in `M2-grader.md`; the researcher decides before M2 runs) | ⬜ | |

## M0b, M2 to M5

Not started. Plans: [`roadmap.md`](roadmap.md).

## Next

1. Merge `umbrella/m1-recheck` into `develop` (a merge commit). Then M2's grader, as decided
   (`docs/experiments/M2-grader.md`, 2026-11-10): the checklist, the majority of three, rule B and
   the noise gate, validated on M1's combined run for consistency only.
2. ADR-0049: the F2 baseline run (an operator the researcher finds), and theme 1 (the change loop).
3. M2's spec, from the draft (`docs/experiments/M2-design.md`): the researcher decides each point,
   freezes the verdict rules, and finds the domain expert who is not the builder; the expert
   writes the change list, seeds it and keeps the key.
4. Push the `v0.1.0` tag on `main` (maintainer); release M1 to `main`.
5. When a domain is shared by several people or agents (M2, or a hosted server): its event
   log moves from git to a database (`--store postgres:DSN` for a composition, one schema per
   member), through a new ADR superseding decision 29A for that case; an export to git can
   keep the audit trail (decided 2026-11-06). Until then the self domains keep their logs in
   git (`domains/<domain>/events/`).
6. ADR-0041's follow-up work (decided 2026-11-06), the third on in
   `umbrella/adr-0041-follow-ups` (#114). Done: approval refuses commits with proposed
   elements, and the change check records how many are left (#110); every decision action takes
   an optional `rationale` (#111); a check can read `actor.principal` (#113);
   `examples/paid-media/` shows the exception pattern (#115); every event records the
   permissions it ran under (#116); a commit may cite its evidence (#117, #118: free strings
   on `commit`, Authoring commit `5-c8fd1b8fc98be17c`), replaced by typed evidence that must
   resolve, cited with `cite_evidence` (#124, in the pstack umbrella).
7. ADR-0042's follow-up work (accepted 2026-11-07): done: `domain_version` with the deployment
   log gives the rule in force when an event was decided, documented, the self domains too
   (ADR-0045, #150); read visibility defined in the schema (`read`, refused until M0b); in M0b,
   deadlines with timers, read visibility enforced by the query and MCP read tools, an observed
   time on facts from adapters, identity mappings on adapters; in M2, `confirmed_at` and
   `review_by` warnings; in the M4 spec, goals, expected outcomes and the outcome-to-decision
   link, with UiPath's Decision Ledger as a reference for what a decision record holds
   (recommendation, evidence, rules and version applied, the person's decision and reason, the
   action, the outcome). A source kind for process mining (event logs of existing systems) is a
   candidate for the authoring interview's sources, with the adapters (M0b).
8. ADR-0043's follow-ups: make `tla` a required check on `develop` (maintainer). Creation
   (#155), link paths to what no action changes (#156) and time, frozen at the harness's clock
   (#157), are modeled; no declaration in the repository leaves anything out.

9. Before M2's Phase B: a probe's starting state written as conditions on objects (for example
   a Commit with `checks_passed` true and `approved` false), and generated from the declarations
   by searching their actions for a way to reach it, instead of a hand-written setup per probe.
   This needs a format change to the probe suite (an ADR). M1 keeps the hand-written setups in
   `experiments/m1/phase_b/probes.py`, built only from the approved tools on a separate domain
   (decided 2026-11-06).

## Left from reviews

Each item names the PR it came from and the review date. The PR that resolves an item deletes
it; each release's cleanup PR handles items older than one release.

None.

## Open questions

- The README now calls brownfield the case Toprope designs for, but the first brownfield adapter
  is planned for M0b, after M1, and M2 does not require one. Make brownfield an actual priority
  (move the adapter earlier, or a brownfield M2)? That would need an ADR changing the roadmap
  order (#102)
- An agent on the researcher's own machine runs with the researcher's git email, so it acts as
  the researcher for every action that does not require a person. Accept this for M1 (the
  decision 30A trust model), or give local agents their own identity? (#85)
