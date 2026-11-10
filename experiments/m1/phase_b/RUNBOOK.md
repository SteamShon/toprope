# Phase B runbook (for the session that runs it)

Link: ① iterate safely, ⑥ (pilot, ADR-0034). How: [ADR-0047](../../../docs/adr/0047-phase-b-runs-from-a-remote-control-session.md),
[ADR-0040](../../../docs/adr/0040-m1-phase-b-execution-protocol.md) and the frozen
[run protocol](../instruments/run-protocol.md).

You are a session the researcher opened through Remote Control on the repository's folder on
their computer. You run the harness there, push the results and open PRs into
`umbrella/m1-phase-b`. Run every command from `experiments/m1`.

## Never
- Open `instruments/change-key.yaml`, `instruments/binding.yaml`, anything in `drafts/`,
  `runs/phase-b/scoring/blind-labels.yaml`, or a run's `recall-questions.yaml`. Do not grep, cat or diff them either. `grade` and `score` open
  what they need.
- Edit what an arm sees: `phase_b/prompts/`, `arms/`, `instruments/`. If something there looks
  wrong, stop and tell the researcher.
- Take a role yourself, or answer a role's question. The harness starts every role.
- Make the researcher's three judgments (marked **STOP** below).

## 0. Set up (once)
```bash
git fetch origin && git switch umbrella/m1-phase-b && git pull
git switch -c exp/m1-phase-b-run          # or continue it, if it exists
uv sync
claude --version                           # the researcher's Claude Code login runs every role
```
If `~/.claude/CLAUDE.md` exists, the harness refuses to start, since it would be added to every role's
context. **STOP**: ask the researcher to move it aside for the run, or to allow it
(`--allow-user-memory`; its hash is recorded).

Ask the researcher which model is under test (`MODEL` below). Every role and the grader use it.

## 1. Freeze the agents' prompts
**STOP**: ask the researcher to read the five prompts in `phase_b/prompts/` (`edit.md`,
`edit_toprope.md`, `review.md`, `probe.md`, `render.md`; not `grade_*`). Say what each is for:
| Prompt | Who gets it |
|---|---|
| `edit.md` | the editor in the NL and structured arms |
| `edit_toprope.md` | the editor in the Toprope arm |
| `review.md` | the reviewer in the NL and structured arms |
| `probe.md` | the probe agent in every arm |
| `render.md` | the agent that writes the NL skill |

Then ask whether each reads as an ordinary request, with no hint of the experiment.

When they say go:
```bash
uv run python -m phase_b freeze-prompts
git add instruments/FROZEN.json
git commit -m "Freeze the Phase B agents' prompts" -m "Frozen at the researcher's instruction (<their words, date>)."
```

## 2. Render the NL skill
```bash
uv run python -m phase_b render --model MODEL
```
It writes `arms/nl/SKILL.md`, `arms/nl/EXAMPLES.md`, `arms/nl.render.jsonl` and
`arms/nl.rendered-from`.

**STOP**: ask the researcher to read `arms/nl/` side by side with `arms/structured/`. Each rule
in the declarations must appear in the skill, and the skill must add none of its own:
- who may take each action
- what each action needs first, and what it changes
- the person-only actions
- the states, and what each refuses
- the invariants
- the handoff
- the glossary

You may list the elements of the declarations to help them check; do not judge the skill yourself.

If they find a fault, do not edit the skill. Render it again:
```bash
rm -rf arms/nl arms/nl.render.jsonl arms/nl.rendered-from
uv run python -m phase_b render --model MODEL
```

When they accept it:
```bash
git add arms/
git commit -m "Render the NL skill from authoring@9 and delivery@1" -m "Reviewed by the researcher (<date>)."
```
Push, and open a PR into `umbrella/m1-phase-b` with steps 1–2.

## 3. Dry run: changes 1 and 2
```bash
uv run python -m phase_b arm nl         --model MODEL --seqs 1-2
uv run python -m phase_b arm structured --model MODEL --seqs 1-2
uv run python -m phase_b arm toprope    --model MODEL --seqs 1-2
uv run python -m phase_b status
```
- The arms may run at the same time, in separate shells; they share the usage limit.
- Exit code 2 means the run stopped: the usage limit, Ctrl-C or an error. Finished changes are
  kept. Run the same command again later to continue.

Report to the researcher:
- The usage each change took, from `status` and each `runs/phase-b/<arm>/seq-NN/record.json` (`tokens`).
  From that, how many usage windows the full run needs.
- Every row of `runs/phase-b-runs.tsv` whose result starts with `error:`.
- Anything odd, for example a review that is empty or truncated.

Do not fix the harness yourself. Report it to the researcher, who will have it fixed in a PR into
the umbrella before the full run.

## 4. Full run: changes 3 to 20
The same commands without `--seqs`. Each continues where its arm stopped:
```bash
uv run python -m phase_b arm nl         --model MODEL
uv run python -m phase_b arm structured --model MODEL
uv run python -m phase_b arm toprope    --model MODEL
```
Repeat after each stop until `status` shows `done 20 of 20` for all three arms. At each stop,
tell the researcher where it stands.

Then:
```bash
git add runs/
git commit -m "Run M1 Phase B on the three arms"
git push
```
Open a PR into `umbrella/m1-phase-b`, or add to the open one.

## 5. Grade
```bash
uv run python -m phase_b grade --model MODEL       # refuses until every arm ran every change
uv run python -m phase_b to-decide
```
`grade` writes `runs/phase-b/scoring/proposed.yaml`. `to-decide` lists only what needs the
researcher:
- flags where the script's and the grader's labels differ
- flags with no label
- edits with no judgment
- probe runs that did not finish

**STOP**: show the researcher each item of `to-decide`, with its flag and the grader's reason, and
record their decision.

Then:
1. Copy `proposed.yaml` to `confirmed.yaml`.
2. Set each decided `label`, edit `fidelity` and probe `passed` as the researcher said. Leave
   `script_label` and `grader_label` as they are.
3. Set `status: confirmed`.

Run `to-decide` again: it must report `count: 0`.

## 6. Score
```bash
uv run python -m phase_b score
git add runs/phase-b/scoring
git commit -m "Score M1 Phase B" -m "Grades confirmed by the researcher (<date>)."
git push
```
Report `runs/phase-b/scoring/metrics.json` to the researcher:
- each arm's recall and precision, with their spread
- the noise floor, and any gap within it (`verdicts.within_noise`)
- the pilot verdicts
- the Toprope arm's iteration time and its limiter

The M1 report (`docs/experiments/M1-self-compile.md`) comes next, in its own PR.

## The M1 recheck (`umbrella/m1-recheck`)

The improved Toprope reruns the same change list from the new baseline (the self domains with their
promoted rules; [`M1-recheck.md`](../../../docs/experiments/M1-recheck.md)). The steps above hold,
with these differences:

- **Branch.** `git fetch origin && git switch umbrella/m1-recheck && git pull`, then
  `git switch -c exp/m1-recheck-run`. PRs go into `umbrella/m1-recheck`.
- **Prompts.** Already frozen: skip step 1. `instruments.py verify --run` must print `ok`.
- **The NL skill** (step 2) is rendered again from the new `arms/structured/` (the old one is
  removed with the re-baseline). The researcher reviews it as before.
- **Every run writes to `runs/phase-b-recheck`**: add `--out runs/phase-b-recheck` to `arm`,
  `status`, `grade`, `to-decide` and `score`. M1's own runs stay as they are.
- **After the three arms**, the combined arm (the Toprope arm with its LLM review):
  ```bash
  uv run python -m phase_b combine-toprope --model MODEL --out runs/phase-b-recheck --to runs/phase-b-recheck-combined
  ```
- **Grade the combined run twice**, in two sittings (exit criterion 3), then compare:
  ```bash
  uv run python -m phase_b grade --model MODEL --out runs/phase-b-recheck-combined
  uv run python -m phase_b grade --model MODEL --out runs/phase-b-recheck-combined --into scoring-2
  uv run python -m phase_b compare-gradings --out runs/phase-b-recheck-combined
  ```
  Report `grader-noise.json`. **STOP** if `within_limit` is false: the researcher decides the
  disagreements that can change recall (M1-recheck.md, criterion 3 as amended):
  ```bash
  uv run python -m phase_b recall-questions --out runs/phase-b-recheck-combined
  ```
  Report only the counts it prints. **Do not open `recall-questions.yaml`**: it holds the answer
  key's entries. The researcher answers each question (`answer: yes` or `no`) in that file, then:
  ```bash
  uv run python -m phase_b apply-recall-answers --out runs/phase-b-recheck-combined
  ```
  It writes `scoring/confirmed.yaml` with `status: proposed`; continue with `to-decide`.
- Then step 5's `to-decide` and confirmation, and step 6's `score`, on
  `runs/phase-b-recheck-combined` (its `scoring/`). Report `metrics.json` with its `probe_gate`
  (exit criterion 1): the probes that fail the gate, and the grader's reason for each failing run.
