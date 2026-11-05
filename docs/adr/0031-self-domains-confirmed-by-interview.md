# ADR-0031: The self domains are confirmed by interview and sign-off, not by a gold set

- Link: ① iterate safely, ⑥ (partial) · Status: accepted · 2026-11-05 · decided by: SteamShon
- Amends: ADR-0030 (decision 3 and 4, revision 3: the correctness set)

## Context
ADR-0030 moved ② to M2 and kept a small frozen **correctness set** for the self domains, as a
guard on the tool M2 builds with and as ⑥'s instrument. Domain Authoring and Domain Delivery
are Toprope's own functions. They are a special case: the owner who knows their rules is the
researcher, who is also present for every step of building them. A gold set adds little
there that the owner's own confirmation does not already give.

## Decision
1. **The self domains are planned and built through the staged interview** (ADR-0025)
   with the researcher. They are judged by no gold set. In M1 they are confirmed by:
   - the researcher's own confirmations during the interview
   - the regeneration check (ADR-0028)
   - the probe suite after each deploy
   - the researcher's sign-off at the switch-over (ADR-0022), the final gate
2. **No correctness set in M1.** A gold file is optional. If the researcher writes one, it
   is validated and frozen with the others, but it is no verdict input.
3. **M1's pre-check instruments are four.** They serve the ① experiment: the probe suite,
   the change requests (against the commit model of ADR-0029), the change key, and the
   verdict rules. Sub-PR 8 waits for these four.
4. **⑥ (partial)** is measured by:
   - handoff-breaking changes caught before deploy (from the change list)
   - the probes that check a handed-off request's intent arrives intact
5. **The self-compile claim** holds if all of these hold:
   - zero hand edits to generated code
   - the regeneration check passes
   - the probes pass
   - the researcher signs off the switch-over

## Consequences
- **Risk.** ADR-0030 revision 3 named one: a wrong self-compiled tool would confound M2. The
  researcher's sign-off, the probes and the regeneration check now carry it. M2 reports, as
  part of its results, any defect traced to the self-compiled tool.
- **Tooling.** `instruments.py` freezes the four files, and a gold file only if present.
- **Documents.** The M1 experiment document, the instrument guide, the verdict-rules draft,
  the instruments README and the M0a spec's sub-PR 8 gate are updated.
