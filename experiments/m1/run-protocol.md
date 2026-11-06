# M1 Phase B run protocol

Link: ① iterate safely (pilot, no verdict; ADR-0034). Status: **draft**. An agent drafted this at
the maintainer's request (PR #121's sub-PR 2). It is not frozen and not used until the
researcher reviews it and freezes it in their own commit, before any arm runs.

It changes no frozen instrument. The verdict rules, change requests, key and binding stay
as they are. Where this protocol would need a verdict rule to change, it says so under
*Questions for the researcher* rather than changing the rule.

It says **how** the three arms of
[`M1-self-compile.md`](../../docs/experiments/M1-self-compile.md) are run and graded, so that
a recall number measures the arm and not the setup. Its rules come from two practices: blind
evaluation of agent behavior, and explaining a measured number before you trust it.

## 1. What the agents in an arm see

The agents in an arm are its LLM reviewer and its probe agent. They see only what the
arm's design gives them.

- **No experiment words.** No directory, file, branch, prompt or tool name an agent sees
  contains `experiment`, `eval`, `arm`, `seeded`, `key`, `judge`, `score`, `benchmark`,
  `recall`, `M1` or `toprope-vs`. Each arm works in its own directory under a project-shaped
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
- **Repeat the stochastic parts.** Run the NL and structured-spec reviewers **3 times** per
  change, with the same prompt, model and settings. Run the probe agents 3 times per change
  in every arm. Run the Toprope arm's checks once: the harness is derandomized. A second run
  of the Toprope arm's checks on 3 changes confirms that its results are the same.
- **Report the spread with every number.** Recall and precision are reported per run, with
  the mean and the minimum and maximum over runs. Probe results are reported the same way.
- **Noise floor.** The noise floor is the largest min-to-max spread of an arm's recall over
  runs. When the gap between two arms is smaller than that, the report says that the gap is
  within run-to-run noise. How that bears on a verdict is a question below.
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

Each run appends rows to one decision log. It is a TSV file, `phase-b-runs.tsv`, and the
researcher decides whether it is committed. Each row has:
`ts`, `arm`, `change`, `run`, `what`, `evidence` and `result`. `evidence` is a pointer, such as a
transcript path, a harness report or a commit, never prose. The log is append-only: a wrong row
is superseded by a new row and never edited. The settings of each run (model, temperature and
tool versions) go in the run's own record. They do not go in a commit message or a PR,
because AGENTS.md keeps model identifiers out of both.

## Questions for the researcher

1. Should a gap within the noise floor make a ① pilot result *inconclusive*? The frozen
   verdict rules do not say. Adding it would be an `amend` of `verdict-rules.yaml`, at your
   instruction.
2. Are 3 runs per stochastic part enough for a pilot, given the cost per run? The design's
   *Cost* metric will show it.
3. Freezing: `instruments.py` freezes a fixed list of files, which does not include this
   one. Should this file get its own entry in `FROZEN.json`, through a requested format change
   to the tool? Or is a commit that sets `Status: frozen` enough?
4. Where do the run records with model names live: in git outside commit messages, or
   outside the repository?
