# ADR-0030: Fidelity (②) is measured on an application domain, not on the self domains

- Link: ① iterate safely, ② model is right · Status: accepted · 2026-11-04 · decided by: SteamShon
  (drafted by the assistant from the researcher's view; revised after an adversarial review)
- Amends: ADR-0002 and ADR-0022 (what M1 gives a verdict on), the roadmap and README
  milestone table, `docs/experiments/M1-self-compile.md`; ADR-0019's ordering is unchanged

> Amended by ADR-0034: M1 gives no link verdict. ① and ⑥ are piloted on the self
> domains; the ① verdict moves to M2, and the self domains' M1 instruments are exempt from
> the human-only rule.

## Context
M1 was to give verdicts on ① (iterate safely) and ② (the model is right) on Toprope's own
self domains, with held-out gold accuracy as the primary measure of ②. Writing that gold set
showed three problems:
- **The answers are not independent.** The researcher who knows the answers also designs the
  system. The agent family that drafts the model also builds the kernel. Keeping held-out
  answers away from the builder took a protocol of its own: isolated sessions, sealed
  validation, excluded sources, fact keys. Even so it stays fragile.
- **Little is left to hold out.**
  - Kernel facts were excluded (ADR-0027).
  - Stage logic and versions were simplified to a commit log (ADR-0029).
  - The public documents state most remaining rules, and Phase A may read them.

  So the self domains offer few facts that are both declarable and unwritten.
- **Toprope's builders are not the users ② is about.** ② is about whether a domain owner's
  tacit knowledge ends up in the model. An application domain, whose expert is not
  Toprope's builder, tests that cleanly. The self domains do not.

## Decision
1. **M1 gives verdicts on ① and on self-compile, not on ②.**
   - **① (primary, unchanged)**: on the frozen change sequence with seeded problems, do
     Toprope's compile-time checks catch what the natural-language and structured-spec arms
     miss (pre-deploy recall and precision, problems found after deploy, iteration time)?
   - **Self-compile (a feasibility result, not a link verdict)**:
     - Are Authoring and Delivery generated end to end from their declarations?
     - Does the regeneration check pass (ADR-0028)?
     - Are there zero hand edits to generated code?
     - Does the switch-over (ADR-0022) happen?
   - **⑥ (partial, unchanged)**: does the typed handoff between the two domains hold across
     changes?
2. **② moves to M2**, on an application domain (the experiment-lifecycle dogfood domain, or
   another chosen in M2's spec PR) whose expert is not Toprope's builder:
   - held-out accuracy (primary), accuracy over iterations, unsupported rules, and human time
   - the P0 sanity check (first-draft accuracy)
   - the gold-set writing protocol built for M1 (`experiments/m1/interview-guide.md`,
     sealed validation, fact keys and compositions, the kernel-fact exclusion), carried over
     as M2's starting point
3. **The self-domain gold set shrinks to a correctness set** (see revision 3): small, frozen,
   for the self tools' critical rules and for ⑥, and not a ② verdict input.
4. **M1's pre-check instruments**: the probe suite, the change requests (re-bound to the
   commit model), the change key, the verdict rules (with the ② rules removed), and the small
   correctness set. Sub-PR 8 (the change check) waits for these.

> Amended by ADR-0031: there is no correctness set. The self domains are confirmed by
> interview, the regeneration check, the probes and the researcher's sign-off.

## Revisions after adversarial review (2026-11-04)
1. **M2's default domain fails this ADR's own premise.** The roadmap's experiment-lifecycle
   domain has "the researcher as owner". *Proposed:* an expert who is not Toprope's builder
   is an **entry criterion for ② in M2**. Without one, ② stays untested rather than being
   reported on weak evidence.
2. **The builder's agent family still drafts the model in M2.** The contamination protocol
   built for M1 carries over unchanged: isolated gold writing, sealed validation, excluded
   sources.
3. **Something must still check that the self domains are right.** M2 builds its domain
   with M1's self-compiled tool. If that tool is wrong, a low ② in M2 cannot be told apart
   from a weak method. ⑥'s "intent survives" measure is also checked by gold questions. The
   regeneration check (ADR-0028) proves the tool is regenerable, not that it is correct.
   *Proposed:* M1 keeps a **small frozen correctness set** for the self tools' critical rules
   and for ⑥. It is not a ② verdict input. It guards the tool M2 depends on, alongside the
   probe suite and the researcher's switch-over sign-off.
4. **Re-bind the change list.** Change requests drafted before ADR-0029 may target version
   states that no longer exist. If they become unbindable, they silently shrink ①'s recall
   denominator. *Proposed:* the change list is reviewed against the commit model before it
   is frozen, and every exclusion is reported in M1's results.
5. **Timeline.** The first ② verdict moves from about week 12 to after M0b and M2 (about week
   20 or later). M2 gains expert recruitment and its first full run of the held-out
   protocol. M2's estimate is redone in its spec PR. M3 may use M2's gold only after M2's
   verdict is frozen.

## Alternatives considered
- **Keep ② on the self domains, with fewer items.** This was rejected because
  the independence problem does not shrink with the item count.
- **Measure ② on both, and weight the application domain.** This was rejected (proposed)
  because it keeps the full cost of the self-domain protocol for evidence it calls weak.

## Affected ADRs, documents and tools (changed with acceptance)

| Item | Change |
|---|---|
| README claim-status table, milestones table | M1: ① ⑥ (+ self-compile); M2: ① ② ③. The `Status` column is untouched (no verdict yet) |
| `docs/roadmap.md` | M1 question and links; M2 gains ② and its held-out protocol |
| `docs/experiments/M1-self-compile.md` | Remove ② from the measures and verdicts; the gold set becomes an optional smoke set; the self-compile measures become explicit |
| ADR-0002, ADR-0022 | Note that M1's self-compile result is a feasibility result; ② is judged in M2 |
| `experiments/tools/instruments.py` | No change: the correctness set is still frozen as `gold-scenarios.yaml` in stage 1 |
| `experiments/m1/` instruments and guide | Not read or changed by the assistant. The researcher decides what to keep of the drafted gold items |
| `docs/milestones/M0a.md` | Sub-PR 8's gate is unchanged (the five stage-1 files, gold being the correctness set) |

## Open questions (for the researcher)
1. The correctness set (revision 3): how small, which rules, and how much of it held out?
2. M2's application domain and its expert (revision 1): who is the expert who is not
   Toprope's builder? If there is none, is ② left untested in M2?
3. The gold items another session has already drafted for the self domains: keep them as
   the smoke set, set them aside for reference, or discard them?
