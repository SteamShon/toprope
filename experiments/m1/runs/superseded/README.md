# Superseded Phase B runs

Link: ① iterate safely, ⑥ (pilot, ADR-0034). Kept as a record; not graded, and not part of the M1
report's numbers.

## `phase-b-2026-11-06/`

The dry run (changes 1–2, #109) and the full run (changes 3–20, #112), run by the researcher on
2026-11-06. They are superseded for two reasons:

1. **Before the run protocol.** They ran before
   [`run-protocol.md`](../../instruments/run-protocol.md) was frozen (2026-11-07). They have one
   review and one probe run per change, where the protocol asks for five reviews, three probe
   runs and the decision log `phase-b-runs.tsv`.
2. **An old baseline.** They start from `authoring@4`. Today's harness finds an invariant break
   in it, so the toolchain's deploy floor refuses it, and Phase B now starts from `authoring@9`
   (`experiments/m1/phase_b/baseline.py`; the researcher's decision, 2026-11-07). The NL skill
   was rendered from `authoring@4`, so it is rendered again.

Their manifests name the instruments, materials, prompts and harness commit they used. The run
directory is kept in git history only (ADR-0055); bring it back with
`python tools/run_archive.py restore experiments/m1/runs/superseded`.
