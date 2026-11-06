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
