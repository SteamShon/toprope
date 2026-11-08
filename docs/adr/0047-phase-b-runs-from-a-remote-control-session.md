# ADR-0047: M1 Phase B runs from a Remote Control session on the researcher's computer

- Link: ① iterate safely, ⑥ (pilot, ADR-0034) · Status: accepted · 2026-11-08 · decided by:
  SteamShon ("the Remote Control way; ADR-0040 is out of date"; drafted by the assistant)
- Supersedes: [ADR-0040](0040-m1-phase-b-execution-protocol.md) §2, and §1's "in an ordinary
  terminal". Brings ADR-0040 in line with the frozen
  [run protocol](../../experiments/m1/instruments/run-protocol.md) and with what was built since.

## Context
ADR-0040 §2 has the researcher type every Phase B command into an ordinary terminal, because an
assistant session can read the repository, and the key is in git. In practice the researcher
works another way: they open a **new** session connected through Remote Control to the
repository's folder on their own computer, and that session runs the commands there, as it did
for earlier steps. The researcher's part is then to start that session, answer it where a
judgment is theirs, and approve what it pushes.

The rest of ADR-0040 is also behind what was built:
- the run protocol (frozen 2026-11-07) asks for five reviews and three probe runs per change, a
  decision log, frozen prompts and blind grading;
- the baseline moved to `authoring@9` (#163);
- the grader runs on the same Claude Code login, not the model API.

## Decision
1. **Who starts a run.** The researcher opens a new session, connected through Remote Control
   to the repository's folder on their computer. That session runs the harness there: `render`,
   `arm`, `status`, `grade`, `score`, and `freeze-prompts` at the researcher's instruction. It
   commits and pushes the results, and opens the PRs into the umbrella. Starting that session and
   giving it the step is the researcher's approval, as typing the command was.
2. **What the launching session never does.** It is not in an arm. So it:
   - never opens `instruments/change-key.yaml`, `instruments/binding.yaml`,
     `experiments/m1/drafts/` or `runs/*/scoring/blind-labels.yaml`;
   - never edits what an arm sees: the prompts, the arms' materials, the change requests;
   - never takes a role (editor, reviewer, probe agent, renderer, grader);
   - never decides the researcher's judgments (below).

   Every role is still a fresh `claude -p` conversation that the harness starts, with no built-in
   tools, only the harness's confined tools, an empty working directory outside the repository,
   and no user memory (ADR-0040 §1 holds). What a role sees does not depend on who started the
   harness.
3. **What stays the researcher's.** The launching session stops and asks at each one:
   - reading the agents' prompts before they are frozen;
   - reading the rendered NL skill side by side with the declarations (the "second reader");
   - confirming the grades. The session lists only what needs a decision: flags where the
     script's and the grader's labels differ, flags with no label, and probe runs that did not
     finish. The researcher decides those and accepts the rest.
4. **The run protocol governs the runs.** Five reviews and three probe runs per change, the
   Toprope arm's repeat and timings, blind grading, the decision log, frozen prompts. It replaces
   ADR-0040 §6's single probe run, and §8's "grader on the model API": the grader runs on the
   same login.
5. **The steps are written down for the session.** `experiments/m1/phase_b/RUNBOOK.md` lists
   them, with each stop for the researcher. A new session starts by reading it.

## Consequences
- The researcher no longer types the harness commands. What they do is start the session, make
  the three judgments, and approve the PRs.
- The launching session reads the repository, so the rule in 2 is text only (review). The roles'
  blindness does not rest on it: it rests on how the harness starts each role, which is tested.
- The run uses the researcher's subscription and its usage limit, as before. A stopped run
  resumes with the same command; the session reports where it stopped.
