# M1 Phase B run protocol

Status: **draft**

Link: ① iterate safely (pilot, no verdict; ADR-0034). An agent drafted this at the maintainer's
request (#123); the researcher decided its open questions on 2026-11-07 (*Decisions*, below).
It is frozen by its hash in `FROZEN.json` (`instruments.py freeze-protocol`) before any arm
runs: `verify --run` refuses a run until then, and a later change goes through `amend`.

It changes no other instrument. The verdict rules, change requests, key and binding stay as
they are; where a verdict rule would be affected, *Decisions* says how it is reported instead.

It says **how** the three arms of
[`M1-self-compile.md`](../../../docs/experiments/M1-self-compile.md) are run and graded, so that
a recall number measures the arm and not the setup. Its rules come from two practices: blind
evaluation of agent behavior, and explaining a measured number before you trust it.

## 1. What the agents in an arm see

The agents in an arm are its LLM reviewer and its probe agent. They see only what the
arm's design gives them.

- **No experiment words.** No directory, file, branch, prompt or tool name an agent sees
  contains `experiment`, `eval`, `arm`, `seeded`, `answer key`, `change key`, `judge`,
  `score`, `benchmark`, `recall` or `M1`. Words a domain's own tools use stay as they are, such as
  the `idempotency_key` every generated action takes. Each arm works in its own directory under a project-shaped
  name, such as `release-process/`.
- **An ordinary request.** The reviewer prompt is what a domain owner would ask before
  deploying, such as "Review this change to our process before we roll it out. Does it conflict
  with anything, or break anything that relies on the old behavior?" The prompt is one fixed
  text per arm, the same for every change, and frozen with this protocol.
- **No hint of the mix.** No agent learns that some changes are seeded, how many, or of
  which type. No agent learns that other arms exist.
- **Fresh context per change.** Each change starts a new agent session. It holds the arm's
  material after the previous changes and the new change request. It holds no earlier
  review or probe output.
- **The key stays sealed.** No agent session mounts or reads `instruments/change-key.yaml`.
  The scorer reads the key, after all arms have run (README, "Keeping the key sealed").

## 2. How flags are graded

- **Flags are taken from what the reviewer wrote.** A flag is a statement that the change
  conflicts with or breaks something named. A summary or a list of the agent's own steps does
  not count. In the Toprope arm, a flag is a finding of the change check or a failed preview
  build.
- **One grader, one pass, sanitized labels.** For each change, the grader sees the three
  arms' flags under random labels (A, B, C). A different random order is used per change,
  and the mapping is kept apart. Every arm is graded on one scale in the same sitting, against
  the bound key entry. The grader is the researcher, or a script where a key entry names an
  element and a flag names the same element.
- **Probe results come from what the agent did.** A probe passes or fails on the actions and
  replies in the probe agent's transcript, not on its own account of what it did.
- **Disagreement is recorded.** When a script and the researcher grade a flag differently,
  both grades are kept and the researcher's grade counts.

## 3. Runs, spread and limiters

LLM review and probe agents vary from run to run. The Toprope arm's checks do not.

- **Write the decision first.** Before the first run, the M1 report's draft states what each
  verdict rule needs (from `verdict-rules.yaml`) and the noise floor below.
- **Repeat the stochastic parts.** Run the NL and structured-spec reviewers **5 times** per
  change, with the same prompt, model and settings. Run the probe agents **3 times** per
  change in every arm. Run the Toprope arm's checks once: the harness is derandomized. A
  second run of the Toprope arm's checks on 3 changes confirms that its results are the same
  (Decision 2).
- **Report the spread with every number.** Recall and precision are reported per run, with
  the mean and the minimum and maximum over runs. Probe results are reported the same way.
- **Noise floor.** The noise floor is the largest min-to-max spread of an arm's recall over
  runs. When the gap between two arms is smaller than that, the report says that the gap is
  within run-to-run noise, next to the verdict rule it affects. The frozen rules are applied as
  they are (Decision 1).
- **Name the limiter of each time.** For iteration time, report the median of 5 timed repeats
  per change, with the spread. Also report what bounds each part, from a profile or timings
  taken during the run: the impact report, the affected harness, or the preview build. A
  time reported without its limiter is incomplete.
- **Rule out the other readings.** Before reporting a number, check:
  - each run did the task (no errored, empty or truncated reviews);
  - no cached result stood in for a run that should have happened (selection misses are
    already a measure);
  - each arm had the same information (the second-reader check in the design's *Risks*).

## 4. The run log

Each run appends rows to one decision log, `experiments/m1/runs/phase-b-runs.tsv`, committed
with the M1 report's data (Decision 4). Each row has:
`ts`, `arm`, `change`, `run`, `what`, `evidence` and `result`. `evidence` is a pointer, such as a
transcript path, a harness report or a commit, never prose. The log is append-only: a wrong row
is superseded by a new row and never edited. The settings of each run (model, temperature and
tool versions) go in the run's own record, `experiments/m1/runs/<arm>/<change>/<run>.json`,
also in git. Run records are the one place model identifiers belong; they still stay out of
commit messages and PRs (AGENTS.md).

## Decisions (researcher, 2026-11-07)

1. **A gap within the noise floor.** The frozen verdict rules are not amended for M1: its
   numbers are pilot targets, not a link verdict (ADR-0034), and changing frozen rules after
   the fact would read as moving the goalposts. The report marks a gap within the noise floor
   next to the rule it affects. M2's preregistered rules take it up, sized by the noise M1
   measures.
2. **Runs.** Reviewers 5 times per change, probe agents 3 times, the Toprope arm once (with
   the 3-change repeat). The reviewers decide the primary measure and its gaps, and a review
   is a single, cheap call; probe agents are long, costly runs for a secondary measure. With
   about 10 seeded problems, one run's recall moves in steps of 0.1; the report says so.
3. **Freezing.** This file is frozen by its hash in `FROZEN.json`, through `freeze-protocol`
   (a format change to `instruments.py`, requested), so `verify --run`, which CI and the
   harness run, enforces it. A `Status:` line alone is checked by nothing.
4. **Where run records live.** In git, under `experiments/m1/runs/`, model names included:
   the model is a variable of the experiment, and the records must stay with the report, the
   commits and the instrument versions they used. AGENTS.md says so as an exception to "no
   model identifiers".
