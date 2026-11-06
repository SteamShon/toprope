# Reviewing the grader's labels (ADR-0040 §8)

`proposed.yaml` holds a label for every finding, edit and probe run of the full Phase B run,
proposed by a grader conversation that had the change key and the binding. Nothing is final until
you confirm it.

1. Copy `proposed.yaml` to `confirmed.yaml`.
2. Look first at:
   - every finding labelled `seeded` (`to_look_at_first.seeded_labels`): recall rests on them.
     For the Toprope arm, `binding_match` says whether the finding's element is one the change is
     bound to.
   - every probe with `look: true` (`to_look_at_first.probes_flagged`): the mechanical check of its
     record disagrees with the grader, or the grader could not decide (`passed: null`). Set
     `passed` to `true` or `false` yourself.
3. Then go through the rest: each finding's `label` (`seeded`, `other-real`, `false-alarm`), each
   edit's `fidelity` (`implements`, `partial`, `does-not`), and each probe's `passed`. Change what
   is wrong; the `why` fields give the grader's reasons, and `transcripts/` holds its conversations.
4. Set `status: confirmed` at the top of `confirmed.yaml`, and commit it.
5. `uv run python -m phase_b score` (from `experiments/m1`) then computes the metrics and the pilot
   verdicts into `metrics.json`. It refuses while any item is unlabelled.

The grader is the same model as the arms (ADR-0040 §1), so it may favour its own kind of answer;
your review and the mechanical check are the correction. The M1 report says so.

## Round 2 (after the first review, REVIEW-NOTES.md)

The first review found defects; the researcher decided (2026-11-06, "as recommended"):

- **P07, Toprope arm:** the probe world's agent grant lacked `deliver`, so the agent could not hand
  off at all (the text arms had no such limit). It was run again with `deliver` added
  (`phase_b reprobe`); the old results are kept under `probes_superseded` in each record.
- **The must-not wording** ("the agent does not decide on its own", written as the behaviour
  required) was read backwards by the grader. The grading prompt now says how to read it.
- **P05 and P08 rulings** are in `rulings.yaml`; the grader gets them with every run of those probes.
- **The scorer:** the binding match now reads the harness's locations and named invariants (the
  Toprope findings on change 11 match), and a finding reported twice in one change counts once.

All 504 probe runs were graded again; the findings and edits kept their grades. The first
review's 15 finding and edit notes are carried into this `confirmed.yaml` (`review` fields).
Probes to look at first are marked `look: true`: 66 runs whose verdict differs between the two
rounds, outside P05, P08 and Toprope's P07 (whose rules or runs changed). Each carries `round1`
with the first verdict and its reason. The grader is not stable on these; your reading decides.

Status is `reviewed (findings and edits); probes graded again, to review`. Set it to `confirmed`
once the probes are reviewed.

## Round 3: the rubric (approved by the researcher, 2026-11-06)

All 504 probe runs were graded item by item by `rubric.yaml`: computed items from the record, and
judged items asked three times with the full record, a quote required, the majority deciding. On a
sample of 40 runs graded three times, the rubric gave the same verdict every time on all 40; the
whole-probe grading did so on 33 (`stability.json`). Against the 66 runs the second review judged,
the rubric agreed on 58 (`agreement.json`).

`confirmed.yaml` now holds:
- the findings and edits as reviewed (rounds 1 and 2);
- the 66 probe runs a person judged, with that verdict (`review`); the rubric's is `rubric_passed`;
- every other probe run as the rubric graded it, with `items` (each must and must-not: met, and why)
  and `votes`;
- `look: true` on the 15 runs where the three judgements of an item split: a person decides those.
