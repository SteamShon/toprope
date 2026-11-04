# M1 instruments

Link: ① iterate safely, ② model is right. Experiment design:
[`docs/experiments/M1-self-compile.md`](../../docs/experiments/M1-self-compile.md).

The templates in `instruments/` define the **format only**. The content is written by the
researcher, and agents must not fill or edit it (AGENTS.md). The one exception is
`verdict-rules`, whose template carries the assistant's draft values for the researcher to
review.

A guide for writing them (coverage areas, what makes a good question, and a session
plan) is in [`interview-guide.md`](interview-guide.md). It holds no content.

## What to fill, and when

| File (copy from `*.template.yaml`) | Shown to | Written | Frozen |
|---|---|---|---|
| `gold-scenarios.yaml` (about 30; half `held_out`) | no arm, ever (held out); answers are graded from the model's read surface | M0a, before change checks are built | M0a |
| `probe-suite.yaml` | no arm before deploy; run after each deploy | M0a | M0a |
| `change-requests.yaml` (about 20, written as **intents**) | all arms | M0a | M0a |
| `change-key.yaml` (seeded problems) | **sealed**: no arm, agent or reviewer during the experiment | M0a | M0a |
| `verdict-rules.yaml` (start from the draft template) | everyone | M0a | M0a |
| `binding.yaml` (intent → element names) | the harness | after Phase A, before any arm runs | then |

The order matters. Freeze everything except the binding **before the change-check pipeline
is built**, so the seeded problems cannot be written around what the checks catch.

## How to freeze
1. Fill the files. Run the validator until it reports no errors:
   ```bash
   uv run --with pyyaml python experiments/tools/instruments.py validate experiments/m1/instruments
   ```
   It checks ids, answer kinds, one key entry per change request, problem types and the
   held-out ratio. It also warns about the key mix, and about request wording that may leak
   the key ("conflict", "break", "seeded").
2. Set `status: frozen` in each file yourself.
3. Run `freeze` (stage 1, in M0a). It freezes the five pre-check files into `FROZEN.json`,
   with a sha256 per file. The binding is ignored at this stage. Commit in **your own
   commit**.
4. After Phase A, write `binding.yaml`, set it `frozen`, and run `freeze-binding`
   (stage 2). This requires stage 1. Commit again.
5. The harness runs `verify --run` before every arm run. It fails if any frozen file changed,
   if any stage-1 file is not frozen, or if the binding is not frozen. Refreezing a changed
   file is refused.

## Keeping the key sealed
`change-key.yaml` lives in the repository for provenance, but no agent run (arm, probe or
reviewer) gets it in its context or mounted files. The harness reads it only when scoring.
If the key is exposed during the experiment, record that in the M1 report.

## Format example (not M1 content)
A filled gold scenario for the *toy experiment domain* in `spikes/m0`, to show the format
only. It is not part of the self domain and must not be reused:
```yaml
- id: G01
  held_out: true
  question: "Can an engineer launch an experiment that is still in draft?"
  answer: {kind: outcome, expected: {result: denied, reason: "Launch requires approval."}}
```
