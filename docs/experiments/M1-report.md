# M1 report: self-compile, and the change sequence (Phase B)

Link: ① iterate safely and ⑥ (the handoff), as a **pilot** (ADR-0034); self-compile feasibility.
Design: [`M1-self-compile.md`](M1-self-compile.md). How Phase B ran:
[ADR-0040](../adr/0040-m1-phase-b-execution-protocol.md),
[ADR-0047](../adr/0047-phase-b-runs-from-a-remote-control-session.md), the frozen
[run protocol](../../experiments/m1/instruments/run-protocol.md). The data:
`experiments/m1/runs/phase-b/` (records, the decision log `phase-b-runs.tsv`,
`scoring/metrics.json`). Written 2026-11-08 by the assistant at the researcher's request; the
researcher's decisions are marked as theirs.

**M1 gives no link verdict.** Its numbers are pilot targets, reported against the frozen verdict
rules to tune the checks and size M2. The README claim-status table does not change.

## Summary
- **The fair comparison favours Toprope over the natural-language skill.** The Toprope arm with
  its LLM review is the declarations, their scenarios, the compiler, and an LLM reviewing the same
  edits (*The fair comparison*, below). Graded blind in the same sitting as the other two arms:
  - Toprope's recall is 0.84 (0.7–0.9), against 0.64 for the NL skill reviewed by an LLM. The gap
    of 0.20 equals the noise floor, so it is at the edge of run-to-run noise.
  - It matches the structured spec reviewed by an LLM (0.84).
  - Grouped precision is about 0.5 in all three arms.
  - On the seven seeded changes that all three arms' edits implemented, recall is 0.94 for
    Toprope, 0.86 for the structured spec and 0.63 for the NL skill. This analysis was added
    after the results, and seven changes are few.
- **Most of the gain comes from the declaration format.** An LLM reading the structured
  declarations does as well on recall as the declarations, compiler and LLM together. The
  compiler's own share is a kind of problem the LLM reviews never caught: the handoff-breaking
  change (9), found by none of the LLM reviews in any run.
- **The compiler alone, as first run, is weak.** The Toprope arm's change check had no
  natural-language checker and no TLC. Against the frozen rules, as preregistered:
  - recall 0.30 and precision 0.09;
  - the pilot verdict for ① is **weakens**;
  - it misses the changes that conflict with a rule, because those rules were bound to actions
    (*Why*).
- **The grader itself varies.** The NL and structured arms were graded again with the combined
  arm, with no new runs, and their recall moved by about 0.1 (0.52→0.64, 0.74→0.84). That is as
  much as the reviews vary. So numbers compare only within one grading. The grader varies as much
  as the arms do, so M2 needs several graders, or the researcher reading every label.
- **The handoff pilot (⑥) is inconclusive.** The handoff-breaking change was caught before deploy,
  but probe P07 fails in every arm, before any change too.
- **Self-compile: not shown to hold.** The tools are generated with no hand edits, the
  regeneration check passes, and the switch-over was signed off. But the probes, run on the
  generated tools before any change, pass 2 of 8. Since probes fail before any change in every
  arm, the probe set-up itself is suspect (see *Limits*).

## The fair comparison: Toprope with its LLM review

Toprope's design pairs the compiler with an LLM (ADR-0009). The arm as first run had only the
compiler. So, at the researcher's request (2026-11-08), the Toprope arm's own edits were reviewed
five times each with the frozen review prompt, as the structured arm's were, and each review's
findings were added to the compiler's flags (`phase_b combine-toprope`, #172; data in
`experiments/m1/runs/phase-b-combined/`). No edit was made again. The three arms were graded blind
in one sitting (#173).

| | NL skill + LLM | Structured spec + LLM | Toprope (declarations, scenarios, compiler, LLM) |
|---|---|---|---|
| Recall, mean (min–max over runs) | 0.64 (0.6–0.7) | 0.84 (0.8–0.9) | 0.84 (0.7–0.9) |
| Precision, every flag counted | 0.51 | 0.47 | 0.22 |
| Precision, a compiler check counted once per change, carried ones left out | 0.51 | 0.47 | 0.48 |
| Seeded changes flagged (in most runs) | 3, 7, 13, 17, 18, 20 | 3, 5, 7, 11, 13, 17, 18, 20 | 3, 5, 7, **9**, 11, 13, 17, 20 |
| Recall on the 7 seeded changes all three edits implemented | 0.63 | 0.86 | 0.94 |
| Edits that implemented the request (of 20) | 18 | 18 | 14 |

What this arm adds, and what it does not show:
- **Added after the first scoring.** The prompts and rules are frozen, and grading is blind. The
  grouped precision and the fidelity-controlled recall were chosen after seeing the results.
- **The LLM does not see the compiler's output.** It reviews the declarations as the structured
  arm's reviewer does. A natural-language check that reads the compiler's impact report, as the
  design has it, is not measured here.
- **The Toprope edits are worse.** Its editor proposes one whole element at a time, and its edits
  implemented the request less often (14 of 20, against 18). A seeded problem an edit did not
  implement cannot be found, which is why recall on the seven changes all edits implemented is
  reported too.
- **The verdict rules do not apply.** They name the Toprope arm as the compiler's change check.
  Applied to this arm, they give "weakens", with both gaps within the noise floor: +0.20 against
  the NL skill and 0.00 against the structured spec. It is reported, not a verdict.

## Phase B results: the compiler alone, as first run

Ten of the twenty change requests carry a seeded problem (bindable; none unbindable). Reviews ran
five times per change, probes three times; the Toprope arm's checks are derandomized and ran once
(again on three changes: the same findings each time).

| | NL skill | Structured spec | Toprope |
|---|---|---|---|
| Pre-deploy recall, mean (min–max over runs) | 0.52 (0.4–0.6) | **0.74** (0.7–0.8) | 0.30 (one run) |
| Pre-deploy precision, mean (min–max) | 0.59 (0.55–0.65) | 0.52 (0.49–0.55) | 0.09 |
| Seeded changes flagged (in most runs) | 3, 7, 13, 17, 20 | 3, 5, 7, 11, 13, 17, 20 | 5, 9, 11 |
| Missed, then surfaced by a probe | 5, 9, 11, 15, 18 | 9, 15, 18 | 7, 13, 15, 17, 20 |
| Silent (never surfaced) | — | — | 3, 18 |
| Recall without the handoff-breaking change | 0.58 | 0.82 | 0.22 |
| Edits that implemented the request (of 20) | 18 (2 partial) | 17 (3 partial) | 14 (4 partial, 2 not) |
| Probe pass rate, mean (min–max) | 0.47 (0.42–0.51) | 0.53 (0.51–0.53) | 0.34 (0.34–0.34) |
| Edit → checked, median per change | 87 s | 103 s | 0.58 s (timed repeats; limiter: preview) |

Recall by the key's problem type:

| Type | NL | Structured | Toprope |
|---|---|---|---|
| conflicts with a rule | 0.8 | **1.0** | 0.2 |
| other: a required stage | 0.8 | **1.0** | 0.0 |
| breaks past behaviour | 0.2 | 0.5 | 0.5 |
| breaks a reference (the handoff) | 0.0 | 0.0 | **1.0** |
| strands objects | 0.0 | 0.4 | 0.0 |

Against the frozen rules (`verdict-rules.yaml`), applied as they are to the mean numbers:
- `iterate`: **weakens**. The Toprope arm's recall is below 0.80, its precision below 0.50, and
  the NL arm is not 30 points lower. The gaps (−0.22 to NL, −0.44 to structured) exceed the
  noise floor (0.20), so they are not run-to-run noise. One run's recall moves in steps of 0.1.
- `handoff`: **inconclusive**. The handoff-breaking change was caught before deploy (1 of 1), but
  P07 does not pass throughout.
- The iteration-time target (median ≤ 1 minute, edit to validated preview) is met by the Toprope
  arm's checks. The timed repeats cover the check and the preview, not the editor's own time
  (about 25 s per change), and use the result cache, as in use.

Cost (estimates): NL $19.92, structured $26.91, Toprope $22.23 for the runs; grading $21.50,
after the recheck $21.74, and for the combined arm $3.92 of reviews and $21.29 of grading.

## Why the Toprope arm missed rule conflicts

The compiler checks a change against what the declarations state. A rule that exists only as a
property of one action is bypassed by a new action. Change 3 ("let an agent confirm elements that
only fix wording") is the clearest case. "Only a person confirms" was `requires: human` on
`confirm_element`. The editor added a new action, `confirm_wording_fix`, that an agent may take.
The new declaration is consistent, and every check passed. An LLM reading the structured spec saw
that it goes around the rule. The same shape recurs in other rule conflicts: the rule a change
conflicts with is an intention about outcomes ("only a person …"), and the declarations bind it to
actions.

The structured spec's lead over the NL skill (+22 points of recall, same model and prompt) comes
from the declaration format alone: the same rules, written down as structure, read better.

## What went wrong in the run, and was fixed

Each was found during the run, fixed in a sub-PR into the umbrella, and the affected part run or
scored again; nothing was edited by hand. The decision log records each superseded attempt.

1. **The baseline.** Today's harness finds an invariant break in `authoring@4`, so the deploy
   floor refuses it. The researcher moved the baseline to `authoring@9` (#163).
2. **An older run's leftovers** (git-ignored caches) were taken for built starting states and a
   run in progress (#167). The first attempt of two arms was set aside.
3. **The Toprope arm's tools drifted.** With ADR-0045, its stand-in ran the arm's own deployed
   changes as tools; change 9 then stopped the arm. It was run again from change 1 (#168).
4. **The Toprope arm's flags were taken on other inputs than the kernel's check.** Every log
   replay finding was lost. The flags were taken again from the stored commits (no model run),
   and all arms were graded again (#169).
5. **The grader sometimes answered in prose,** and its verdict was lost; the researcher decided
   those (six probe runs). It is now asked again for JSON (#174).

The first full run (2026-11-06) is superseded: it ran before the run protocol was frozen, and from
`authoring@4` (`experiments/m1/runs/superseded/`).

## Limits
- **Seeding bias.** The builder of the checks chose the seeded problems, and the harness's author
  had seen the key (ADR-0040 §9). Its prompts were reviewed and frozen by the researcher.
- **Small numbers.** Ten seeded problems, one domain pair, and one run of the Toprope arm.
- **The Toprope arm was incomplete.** Neither the natural-language check nor TLC ran. The
  combined arm adds an LLM review, but not one that reads the compiler's output.
- **The grader varies.** One grader graded the same flags about 0.1 of recall apart in two
  sittings. That is as much as the reviews vary, and it is not part of the noise floor.
- **The probes are suspect.** Several fail before any change in every arm (P07 everywhere; in the
  Toprope arm six of eight). So "found after deploy" and the probe pass rates measure the probes
  as much as the arms. When the grader answered in prose, its verdict was lost and the researcher
  decided it (four probe runs over the two gradings).
- **Precision counts every flag.** The log replay reports one warning per past action re-decided,
  up to 64 for one change, so a few changes dominate the Toprope arm's precision.
- **The stand-in.** It took the person-only steps in the sandbox (ADR-0040 §5). M1 does not test
  the researcher's own approval habits.

## What M2 takes from this
These are questions for M2. Their answers are M2's, on a domain and change list the builder did
not write; nothing below is tested by M1's numbers.

1. **Rules bound to outcomes.** A rule such as "only a person makes an element confirmed" attaches
   to the state or property, so every action that reaches it is held to it. Does that let the
   compiler catch rule conflicts?
2. **A capability diff in the change check.** Before and after a change: who (person, agent,
   system) can reach which state, under which preconditions. A widening is a finding.
3. **The full Toprope check.** The compiler, TLC, and a natural-language check that reads the
   structured diff with the impact report. Compare it with a structured spec reviewed by an LLM.
   M1 found them level on recall (0.84 each) when the LLM did not see the compiler's output. The
   question to preregister: does the full check beat the structured spec in both recall and
   precision? If not, Toprope's value narrows to its declaration format and to the classes of
   problem only the compiler catches.
4. **Grouped warnings.** One flag per check and element, with a count; what the base carried is
   shown apart.
5. **An editor that proposes a patch.** It proposes several elements at once and sees them
   checked, instead of one whole element at a time.
6. **A steadier grader.** Several graders, or the researcher reading every label, since one
   grader varied by about 0.1 of recall between two sittings.
7. **Probes that pass before any change.** Fix their starting states and criteria, and have the
   grader asked again when it does not answer in JSON (done in #174).
