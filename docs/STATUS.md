# Status

Link: none (enabler). A snapshot of what is done and what is left, and nothing else. History
lives in git, the PRs and the ADRs (`git log -- docs/STATUS.md` shows which PR last changed
this page); plans live in [`roadmap.md`](roadmap.md) and the milestone and experiment docs.
Every PR into `develop` or an `umbrella/*` branch fixes any line here it makes untrue, or says
why not; each release trims it ([`AGENTS.md`](../AGENTS.md), "Progress").

Updated: 2026-11-06 · Cleaned for release: `v0.1.0`

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
| Phase A: the Authoring and Delivery self domains, built and confirmed | ✅ | #69, #73, #74 |
| First self-domain commits approved | ✅ | #77 |
| Domain guide at preview | ✅ | #67 |
| Mechanical harness layer (ADR-0035) | ✅ | #71 |
| Domain commit store kept in git | ✅ | #75 |
| Generated `toprope-run` and how-to-work guide (ADR-0036) | ✅ | #76 |
| Switch-over (ADR-0037, umbrella #81): only the kernel stays hand-built | ✅ | #81 |
| Phase B: the change sequence on the three arms (umbrella `umbrella/m1-phase-b`) | 🟡 | |
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

### Phase B (umbrella `umbrella/m1-phase-b`)

| Sub-PR | Status | PR |
|---|---|---|
| 1. Execution protocol (ADR-0040); amended in 2a to run on the researcher's own Claude Code, on their machine | ✅ | #98 |
| 2a. Harness core: each role a fresh `claude -p` with only the harness's confined tools; stop at the usage limit and resume; progress line; the NL and structured-spec arms; the NL skill's rendering. Tested with a fake model and a fake `claude` | ✅ | #100 |
| 2b. The Toprope arm: a sandbox with fixed tools, the compiler's checks and a preview, the stand-in for person-only steps and its override of a failed check (the floors still hold). Tested on the real kernel | ✅ | #101 |
| 2c. The probes: eight starting states built once per run with the approved tools (a small `library` domain), the same generic tools in every arm, the deployed domains' generated MCP in the Toprope arm; the probe agent never sees what a probe checks | ✅ | #103 |
| 3. The three arms' materials (`experiments/m1/arms/`): structured and Toprope built from the approved commits, the NL skill rendered blind; reviewed side by side by the researcher | 🟡 | #105 |
| 4. Scorer (`grade` proposes labels with a grader, `score` computes the metrics and pilot verdicts from the researcher's confirmed labels; the key opens only here and only after every arm ran every change), tested with a synthetic key; the probes now also run once before any change | 🟡 | #106 |
| 5. Dry run (changes 1–2), run by the researcher: time and usage per change | ✅ | #109 |
| 6. Full run, scoring confirmed by the researcher, M1 report | 🟡 | #112 |

How a run works: the researcher runs `python -m phase_b arm ARM --model M` (from
`experiments/m1`) in an ordinary terminal. Each conversation is written as it happens, and
running the same command again continues a stopped run (ADR-0040 §1–2). The probes after each
change run four at a time (`--jobs`); they are independent, each on its own copy of its starting
state.

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

## M0b, M2 to M5

Not started. Plans: [`roadmap.md`](roadmap.md).

## Next

1. M1 Phase B as ADR-0040 sets out (sub-PRs above): the arms' materials, the runner, the
   scorer, a dry run, then the full run and the M1 report. The researcher runs both runs from
   their own terminal, on their Claude Code login; nothing to set up in GitHub.
2. Push the `v0.1.0` tag on `main` (maintainer); release M1 to `main`.
3. Before M2 (a domain whose sources may be private): a kernel `read_source` MCP tool that
   serves source text with redaction and refuses local-only sources, as the removed authoring
   MCP did. A read, not an action: the text never goes into an event log (decided 2026-11-06).
   Until then agents get references from `search` and read files directly, which is safe for
   the self domains (no local-only sources; the agent already sees the repository).
4. When a domain is shared by several people or agents (M2, or a hosted server): its event
   log moves from git to a database (`--store postgres:DSN` for a composition, one schema per
   member), through a new ADR superseding decision 29A for that case; an export to git can
   keep the audit trail (decided 2026-11-06). Until then the self domains keep their logs in
   git (`domains/<domain>/events/`).

5. Before M2's Phase B: a probe's starting state written as conditions on objects (for example
   a Commit with `checks_passed` true and `approved` false), and generated from the declarations
   by searching their actions for a way to reach it, instead of a hand-written setup per probe.
   This needs a format change to the probe suite (an ADR). M1 keeps the hand-written setups in
   `experiments/m1/phase_b/probes.py`, built only from the approved tools on a separate domain
   (decided 2026-11-06).

## Left from reviews

Each item names the PR it came from and the review date. The PR that resolves an item deletes
it; each release's cleanup PR handles items older than one release.

- `then` in `toprope-run` reads only the target's stream, so a call or handoff set off on
  another stream (for example by a newly created object) is not shown (#86, 2026-11-06)
- The effect-resolution summary is written twice, in `toprope-run` (`followed`) and in the
  regeneration check (`_one`); factor one helper onto `Outbox` (#86, 2026-11-06)
- Neither the validator nor the harness catches a creating action that leaves a required
  property unset (`record_commit` made Commits without `domain_id`; found running the loop)
  (#86, 2026-11-06)
- `propose_element` on a path that is not an element (for example `glossary.<term>`) writes the
  value without provenance instead of failing (#86, 2026-11-06)
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
- Authoring's `record_questions` sets the stage and the bundle but not `params.questions`, so the
  generated tools never show the bundle's questions (`next_questions` returns only the bundle id).
  Found building probe P04's starting state (#103, 2026-11-06). Not fixed in M1: the self domains
  are the experiment's baseline
- The mechanical layer computes `unreachable_from_creation` twice per run (#71, 2026-11-05)
- `merge_main` writes the working copy and records the merge in progress in two steps; a
  commit from another process between them gets one parent, and the next commit a stale
  second one (#89, 2026-11-06)
- The kernel reference generator reads private `argparse` attributes (`_actions`,
  `_SubParsersAction`); a Python release that renames them breaks it (#89, 2026-11-06)
- `Workspace.confirm` and `approve_commit` still name the removed channels (`cli`,
  `elicitation`) (#89, 2026-11-06)

## Open questions

- An agent on the researcher's own machine runs with the researcher's git email, so it acts as
  the researcher for every action that does not require a person. Accept this for M1 (the
  decision 30A trust model), or give local agents their own identity? (#85)
