# ADR-0040: How M1 Phase B runs

- Link: ① iterate safely, ⑥ org productivity (pilot, ADR-0034) · Status: accepted ·
  2026-11-06 · decided by: SteamShon (D1–D4 "as recommended"; drafted by the assistant).
  Amended the same day by SteamShon: §1 and §2 run on the researcher's own Claude Code, on
  their machine, instead of the model API in GitHub Actions (no API key; the CI setup cost more
  than the run)
- Refines: [`M1-self-compile.md`](../experiments/M1-self-compile.md) Phase B; ADR-0034

## Context
Phase B applies the 20 frozen change requests, in order, to three arms (natural-language
skill, structured spec, Toprope). It then measures how many seeded problems each arm's
pre-deploy check flags, and what the post-deploy probes surface. The design doc says what is
measured. It leaves open who runs the arms, where, and what happens at the steps only a
person may take.

One fact shapes the answer. The assistant session that drafted the change-key options and
the binding has seen the key. If it played an arm's editor, reviewer or probe agent, the run
would not be blind. A coding-agent subagent is no better, because it can read the repository,
and the key is in git.

## Decision
1. **A harness runs every role as a fresh conversation** on the researcher's own Claude Code
   (`claude -p`, their subscription). The roles are editor, reviewer, probe and grader. Each
   conversation's context holds only:
   - a fixed, generic prompt for its role, as the whole system prompt,
   - its arm's materials,
   - the tools the harness defines.

   How the harness keeps each conversation blind:
   - **No built-in tools.** Claude Code's own tools are off: no file reads, no shell.
   - **Only the harness's tools.** They are served over MCP and confined to the arm's
     workspace, and the conversation loads no other MCP server.
   - **No project files.** It runs in an empty directory outside the repository, so no
     project CLAUDE.md or project settings load.
   - **No user memory.** The run refuses to start when `~/.claude/CLAUDE.md` exists, unless
     the researcher allows it; the run then records its hash.
   - **Checked at the start.** The conversation's init event must list only the harness's
     tools, or the run stops.

   No role gets the repository, `change-key.yaml`, `binding.yaml`, the option drafts or the
   working notes. The harness records every conversation and its token use. The model API is
   kept as an alternative backend, for a run with an API key.
2. **The researcher runs it on their own machine, in an ordinary terminal.** It does not run in
   an assistant session, which can read the repository, and starting it is the researcher's
   approval. The run is bounded by the subscription's usage limits rather than a dollar cap:
   - **Stopping is safe.** Reaching the limit, or Ctrl-C, stops it and keeps every finished
     change.
   - **Resuming is the same command.** It continues where the run stopped, and refuses to
     resume with another model, other materials, instruments or prompts.
   - **The run is visible.** A progress line shows the arm, the change, the role and the turn,
     and every conversation is written as it happens.
   - **The results come back as a PR.** The researcher commits the run directory in their own
     PR.
3. **The arms start from the same approved models**, `authoring@9-b4ec65433222f096` and
   `delivery@1-584aaeea5e686ee8` (amended 2026-11-07 by SteamShon: first `authoring@4`, which
   today's harness finds an invariant break in, so the deploy floor refuses it; `@9` is the first
   approved commit after the fix, and from `@4` to `@9` elements were only added. The binding's
   `domain_version` was amended to match):
   - **NL arm:** a SKILL.md with examples, rendered from the declarations by a fresh agent
     that has never seen the key.
   - **Structured-spec arm:** the declarations and the composition's handoffs, as text.
   - **Toprope arm:** a sandbox with copies of the declarations, the commit store and the
     domains' event logs, so that log replay has history to replay.

   The researcher reads the three side by side and checks that every rule appears in each
   (the design's "second reader"). Their materials are hashed into the run's manifest. The
   real self domains are never changed by the experiment.
4. **Every change is deployed, flagged or not (D1).** The arms then pass through the same
   sequence of states, so their numbers compare. A flag is recorded as the arm's pre-deploy
   finding; it does not stop the change.

   **In the Toprope arm**, approval itself refuses a commit whose check failed. The researcher
   decided (2026-11-06):
   - The stand-in records an override approval in the sandbox's commit store, and the commit
     is previewed and deployed through the kernel.
   - The kernel's floors still hold: a valid declaration, and a passing build harness.
   - When a floor refuses, the change is recorded as undeployable, and the working copy goes
     back to `main`, the last deployed state.

   The build harness runs the declared scenarios, as the scenario check does. So a change
   that breaks a scenario is usually undeployable, and from there the Toprope arm's states
   differ from the other arms'. The report states which changes did not deploy.
5. **In the sandbox, a stand-in for the researcher takes the person-only steps (D2).** These
   are confirming, approving and deploying, taken by the harness under an identity named
   `researcher-standin`, and the report says so.
   - The sandbox's changes are hypothetical, and some are bad on purpose. Approving them as
     the researcher, roughly 60 times, would record decisions the researcher did not make.
   - Probes that ask an agent to take a person-only step (P01, P05) still run against the
     arm. The stand-in is the harness, never the probed agent.
6. **The probes run after every change (D3).** All eight probes run after each of the 20
   changes, in all three arms. A dry run on the first two changes measures time and cost
   before the full run is approved; the researcher may then change the cap, not the protocol.
7. **The model under test is experiment data (D4).** All roles in all arms use the same
   model.
   - Its id is an Actions variable, and the run manifest records it as the thing measured.
   - AGENTS.md's rule against model identifiers is about attribution, so it does not apply
     here.
   - Code, commits and PR texts still name no model.
8. **The key is opened only by the scorer.** Scoring happens after all arms have run.
   - **Toprope findings** name elements, so they match the binding mechanically.
   - **Prose findings and probe failures** are matched by a grader, a fresh API
     conversation that does get the key and the binding.
   - **Edit fidelity:** the grader also judges whether each arm's edit implemented the
     intent. Without that, a bad edit and a missed check would look the same.
   - **The researcher confirms every match** in the scoring PR.
   - The verdict rules (`verdict-rules.yaml`) are then applied as frozen.
9. **What the M1 report states.** It states that the harness's author had seen the key, and
   that its prompts are generic and were reviewed by the researcher before the run.

## Consequences
- The researcher's part:
  - reviewing the three arms' materials,
  - running the dry run, then the full run, from their terminal,
  - committing the results,
  - confirming the scoring.

  Nothing else waits on them.
- Runs are reproducible from the manifest: the materials' hashes, the instruments' hashes
  (`instruments.py verify --run` runs first), the prompts, the model and the harness commit.
- The stand-in means M1 does not test the researcher's own approval habits; M2 does, with an
  expert who is not the builder.
- The run is about 480 probe conversations plus 60 edits and 40 reviews. The dry run shows how
  much of the usage limit one change takes, so the full run can be planned across limit windows.
  The same usage limit covers the researcher's other use of Claude.
