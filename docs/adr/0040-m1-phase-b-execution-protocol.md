# ADR-0040: How M1 Phase B runs

- Link: ① iterate safely, ⑥ org productivity (pilot, ADR-0034) · Status: accepted ·
  2026-11-06 · decided by: SteamShon (D1–D4 "as recommended"; drafted by the assistant)
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
1. **A harness runs the arms through the model API.** Each agent role (editor, reviewer,
   probe, grader) is a fresh API conversation. Its context holds only:
   - a fixed, generic prompt for its role,
   - its arm's materials,
   - the tools the harness defines.

   No role gets the repository, `change-key.yaml`, `binding.yaml`, the option drafts or the
   working notes. The harness records every conversation, its token use and cost.
2. **It runs in GitHub Actions, after the researcher approves.** It does not run in an
   assistant session. The workflow waits on the `researcher` environment (ADR-0039), as human
   requests do. The API key is a repository secret, and the run stops at a cost cap the
   researcher sets.
3. **The arms start from the same approved models**, `authoring@4-b0c8834e25d9bbc7` and
   `delivery@1-584aaeea5e686ee8`:
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
  - adding the API key and the cost cap,
  - reviewing the three arms' materials,
  - approving the dry run and the full run,
  - confirming the scoring.

  Nothing else waits on them.
- Runs are reproducible from the manifest: the materials' hashes, the instruments' hashes
  (`instruments.py verify --run` runs first), the prompts, the model and the harness commit.
- The stand-in means M1 does not test the researcher's own approval habits; M2 does, with an
  expert who is not the builder.
- The cost is about 480 probe conversations plus 60 edits and 40 reviews. The dry run turns
  that into a number before anything large is spent.
