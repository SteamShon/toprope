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
| M1 self-compile | ① ⑥ pilot, no verdict | 🟡 | Phase A done; switch-over in progress; Phase B not started |
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
| Change requests and the sealed change key (researcher; options drafted on request, ADR-0034) | ⬜ | |
| Binding, frozen after Phase A | ⬜ | |
| Phase A: the Authoring and Delivery self domains, built and confirmed | ✅ | #69, #73, #74 |
| First self-domain commits approved | ✅ | #77 |
| Domain guide at preview | ✅ | #67 |
| Mechanical harness layer (ADR-0035) | ✅ | #71 |
| Domain commit store kept in git | ✅ | #75 |
| Generated `toprope-run` and how-to-work guide (ADR-0036) | ✅ | #76 |
| Switch-over (ADR-0037, umbrella #81): only the kernel stays hand-built | 🟡 | below |
| Phase B: the change sequence on the three arms | ⬜ | |
| M1 report ([`experiments/M1-self-compile.md`](experiments/M1-self-compile.md)) | ⬜ | |

### Switch-over (umbrella #81)

| Sub-PR | Status | PR |
|---|---|---|
| 1. Workspace into the kernel; interview operations as kernel services | ✅ | #80 |
| 2. Per-domain layout and a JSONL event store in git; Authoring calls the interview services | ✅ | #82, #83 |
| 3. `toprope-run` as yourself from your git identity (`toprope.identity.yaml`) | ✅ | #85 |
| 4. The whole loop on the generated tools, end to end; the regeneration check passes | ✅ | #86 |
| 5. Remove `toprope-author`, `toprope-deploy` and their hand-written guides; generate the kernel's command reference | 🟡 merge, checkout and confirm-all declared (proposed); removal next | #89 |
| Researcher sign-off; the umbrella merges into `develop` | ⬜ | |

Sub-PRs 1–4 are on the umbrella branch, not yet on `develop`.

### How the self domains run (on the umbrella branch)

- `toprope-run --composition domains/toprope-self.composition.yaml --member <m>` runs the whole
  loop (commands in [`workflow.md`](workflow.md)). Each member's events go to its own
  append-only log, `domains/<domain>/events/`, kept in git; example objects never go into it.
- You are your git email, looked up in `toprope.identity.yaml`. An agent on your machine has
  your git email too; an `agents` entry applies only to an agent with its own email. Actions
  that require a person also ask on your terminal: a guard against mistakes, not a boundary.
- `toprope-run` reports what a command set off (`then`): each kernel call, its reply, the
  object a creating reply made (for example the new commit's id), and each handoff.

## M0b, M2 to M5

Not started. Plans: [`roadmap.md`](roadmap.md).

## Next

1. Switch-over sub-PR 5, then the researcher's sign-off and the umbrella merge.
2. M1 instruments, the rest (researcher): the change requests and the sealed change key, frozen
   before the pilot runs; then the binding ([`experiments/m1/README.md`](../experiments/m1/README.md)).
3. M1 Phase B, then the M1 report.
4. Push the `v0.1.0` tag on `main` (maintainer); release M1 to `main`.

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
  differently (the identity file's name vs git `user.name`); goes away with sub-PR 5
  (#85, 2026-11-06)
- The mechanical layer computes `unreachable_from_creation` twice per run (#71, 2026-11-05)

## Open questions

- An agent on the researcher's own machine runs with the researcher's git email, so it acts as
  the researcher for every action that does not require a person. Accept this for M1 (the
  decision 30A trust model), or give local agents their own identity? (#85)
