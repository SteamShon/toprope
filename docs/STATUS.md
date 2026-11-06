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

## M0b, M2 to M5

Not started. Plans: [`roadmap.md`](roadmap.md).

## Next

1. M1 Phase B: the change sequence on the three arms (every M1 instrument is frozen; the
   harness runs `instruments.py verify --run` before each arm run), then the M1 report.
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
5. ADR-0041's follow-up work, one PR each (decided 2026-11-06), in
   `umbrella/adr-0041-follow-ups` from the third on. Done: approval refuses commits with
   proposed elements, and the change check records how many are left; every decision action
   takes an optional `rationale`, stored with the decision; a check can read `actor.principal`;
   `examples/paid-media/` shows the exception pattern; every event records the permissions it
   ran under. Left: an optional evidence field on commits (it changes the Authoring
   declaration, so it goes through the self domains' own loop and needs the researcher's
   approval).

## Left from reviews

Each item names the PR it came from and the review date. The PR that resolves an item deletes
it; each release's cleanup PR handles items older than one release.

- Nothing keeps the author of a commit from approving it: `approve_commit` checks only that a
  person approves (`requires: human`) a commit whose checks passed. Charter §5 says "no
  self-approval"; ADR-0032 keeps one approver in M1. Decide whether to enforce author ≠
  approver before M2, when a domain gets more than one owner (#102, 2026-11-06)
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
- The mechanical layer computes `unreachable_from_creation` twice per run (#71, 2026-11-05)
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
