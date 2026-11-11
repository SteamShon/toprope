# ADR-0034: M1 pilots ① on the self domains; the ① verdict moves to M2

- Link: ① iterate safely, ⑥ org productivity · Status: accepted · 2026-11-05 · decided by:
  SteamShon (direction "Y" and the open questions; drafted by the assistant)
- Amends: ADR-0030 (what M1 gives verdicts on), ADR-0031 (M1's instruments), AGENTS.md (the
  human-only rule), `docs/experiments/M1-self-compile.md`, the roadmap and README milestone
  table, `docs/milestones/M0a.md` (sub-PR 8's gate)

> Amended by ADR-0054: M2's change requests come from the researcher; the problems are seeded,
> and the key kept, by a person who is not Toprope's builder. ① keeps its verdict, with that limit.

## Context
ADR-0030 moved ② out of M1. Its reason was that the builder's answers are not independent
evidence about a domain the builder designed. The same reason applies to ①, M1's remaining
link verdict.
- **The seeded problems are not independent of the checks.** The researcher designs the
  change-check pipeline, and the assistant's agent family builds it (M0a sub-PR 8). The
  same people choose the problems those checks are scored on. M1's own risk list names this
  ("seeding bias"). Writing the change list alone and sealing the key reduce the bias, but
  do not remove it.
- **The protocol is costly for weak evidence.** The researcher writes about 20 intents and
  a key alone, and they are frozen and sealed before the checks are built. Agents cannot
  help with the content, even by offering choices. Sub-PR 8 waits on all of this.
- **M2 has the independence M1 lacks.** M2's application domain needs an expert who is not
  Toprope's builder (ADR-0030, revision 1). That expert's own change requests are
  independent of the checks, without any protocol.

## Decision
1. **M1 gives no link verdict.** It reports:
   - **Self-compile** (a feasibility result, unchanged): generated end to end, the
     regeneration check passes, zero hand edits to generated code, the switch-over is
     signed off, and the probes pass.
   - **① as a pilot.** The three arms run on a change sequence with seeded problems, as
     designed, and recall, precision, iteration time and the check breakdown are reported.
     The numbers tune the checks and size M2's run. They are not evidence for ①, and the
     claim-status table does not change on them.
   - **⑥ as a pilot.** The handoff measures (P07, handoff-breaking changes caught) are
     reported the same way.
2. **The ① verdict moves to M2**, on the application domain:
   - the change requests come from the expert who is not Toprope's builder
   - M1's verdict rules for ① and ⑥ carry over as M2's starting point, frozen in M2's spec PR
   - without such an expert, ① stays untested in M2, as ② does (ADR-0030)
3. **The self domains' instruments are an exception to the human-only rule.** For M1's
   self-domain instruments (the probe suite, the change requests, the change key and the
   verdict rules):
   - an agent may draft their content when the researcher asks, including multiple-choice
     options the researcher selects from
   - the researcher reviews, selects and freezes them in their own commit
   - they are still frozen before the pilot runs, so the pilot is not tuned to its own
     results; sealing the key from agents is no longer required
   - the human-only rule stays unchanged for everything that feeds a link verdict: M2 and
     later instruments, and any gold set
4. **Sub-PR 8 (the change check) no longer waits for the M1 instruments.** Its gate becomes
   the probe suite and the verdict rules, which exist. The change requests and key are
   frozen before the pilot run, not before the checks are built.

## Consequences
- **Earlier progress.** Sub-PR 8 and 9 can start now, and the umbrella can move toward
  `develop` sooner.
- **The first ① verdict comes later.** It moves to M2, after M0b (about week 20 or later),
  and it depends on recruiting an expert who is not the builder.
- **M1's ① numbers have a defined use.** They tune the checks and size M2. They are
  reported as a pilot and never cited as support.
- **The protocol built for M1** (the interview guide, sealed validation, the change-type
  menu) carries over to M2 unchanged, where the human-only rule still applies.

## Affected documents and tools (changed with acceptance)

| Item | Change |
|---|---|
| README milestones table | M1: self-compile (feasibility) + ① ⑥ pilot; M2: ① ② ③. The `Status` column is untouched |
| `docs/roadmap.md` | M1 question and links; M2 gains the ① verdict |
| `docs/experiments/M1-self-compile.md` | verdict rules become pilot targets; ① and ⑥ reported, not judged |
| `experiments/m1/instruments/verdict-rules.yaml` | `iterate` and `handoff` marked as pilot targets (the researcher's draft; values unchanged) |
| `experiments/m1/interview-guide.md` | the change list and key may be drafted with agent help, by multiple choice |
| AGENTS.md | the self-domain exception in "Gold sets are human-only" |
| `docs/milestones/M0a.md` | sub-PR 8's gate: the probe suite and the verdict rules |
| ADR-0030, ADR-0031 | a note pointing here |
| `experiments/tools/instruments.py` | `verify` for sub-PR 8 requires the probe suite and verdict rules only; the change list and key are required before the pilot run (`--run`) |

## Alternatives considered
- **Keep ① in M1 with the protocol (X).** Rejected: the independence problem
  does not shrink with more protocol, the same argument ADR-0030 made for ②.
- **Exempt the self domains but keep the ① verdict in M1.** Rejected: agent-drafted
  seeded problems scored against agent-built checks would make the verdict circular.

## Resolved (researcher, 2026-11-05)
1. **⑥ in M1 is a pilot**, like ①. "The handoff holds" (P07) is reported, not judged.
2. **M2's seeded problems** (who seeds them into the expert's requests, and who writes the
   key) are decided in M2's spec PR.
3. **The pilot runs all three arms** (natural-language skill, structured spec, Toprope), so
   its numbers are comparable and size M2's run.
