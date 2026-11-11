# ADR-0054: M2 runs on the researcher's own paper trading; an outside person seeds the problems

- Link: ① iterate safely, ② model is right, ③ works as built (what M2 judges) · Status: **accepted**
  (1–5), 2026-11-11, decided by SteamShon (option B; the domain; a paper-trading account; daily
  use), drafted by the assistant · open questions below
- Amends: ADR-0030 (② in M2 needs an expert who is not the builder), ADR-0034 §2 (the ① verdict's
  change requests), `docs/roadmap.md` (M2's domain and its brownfield effect), the README
  claim-status and milestone tables (where ② is tested; the `Status` column is untouched),
  `docs/experiments/M2-design.md`

## Context
ADR-0030 and ADR-0034 made M2's ① and ② verdicts depend on a domain expert who is not Toprope's
builder. The roadmap's candidate, the experiment lifecycle, has the researcher as owner, which
fails that condition (ADR-0030, revision 1). No outside expert is available for three to four
weeks. The researcher runs no business domain at the moment.

M2 also judges ③, which needs someone to use the generated tool for real for at least two weeks.
An outside expert would rarely do that. The researcher would.

Candidates considered (2026-11-11): the experiment lifecycle, Meta ad operations, a job-search
pipeline, project tracking, and the researcher's own stock investing. Stock investing fits best:

| Need | Stock investing on a paper account |
|---|---|
| The researcher knows the rules | they are the researcher's own investing rules |
| States and rules to seed problems into | idea → research → order proposed → approved → placed → filled, part filled or cancelled → held → sold; position limits, cash floor, stop-loss, no buying before earnings |
| Real use for ③ | daily trading or checking, on a paper (모의투자) account: real prices, no money at risk |
| A brownfield effect | the broker's paper-trading API: an order, and its result read back |
| Not contaminated | nothing in `examples/` or the templates covers trading. Meta ads would overlap `examples/paid-media`; project tracking would overlap the self domains |
| The agent proposes, a person approves | the agent proposes orders; the researcher's rules gate them; the researcher approves |

The cost is independence. ADR-0034's reason for moving ① out of M1 was that the people who build
the checks also chose the problems scored against them. ADR-0030's reason for ② was that the
builder's answers are not independent evidence about a domain the builder designed.

## Decision
1. **M2's domain is the researcher's own stock investing, on a paper-trading account.** The
   researcher is the expert, the owner and the user. What the domain contains (states, actions,
   rules, outcome rules) comes from the researcher's interview, not from this ADR. No live
   brokerage account is connected in M2.
2. **Roles (option B).**

   | Role | Who | Does |
   |---|---|---|
   | Expert and owner | the researcher | answers the interview; writes the change requests, the probes and any gold |
   | Seeder | one person who is not Toprope's builder (about 1–2 hours) | seeds the problems into the change requests; writes and keeps the key |
   | User (③) | the researcher | trades or checks daily for at least two weeks with the generated tool |
   | Builder | the researcher and the assistant | the tool, the harness, the grader; no instrument content |

   The human-only rule (AGENTS.md) is unchanged: M2's change requests, seeds, key, probes, binding
   and any gold set are written by people. An agent drafts none of their content.
3. **What M2 judges.**
   - **① gets a verdict.** The independence ADR-0034 asked for sits in the seeding and the key,
     which the seeder holds. The change requests come from the builder. That is reported with the
     verdict as a stated limit. It amends ADR-0034 §2, which asked for change requests from an
     expert who is not the builder.
   - **② gets no verdict in M2.** The held-out protocol (ADR-0030, decision 2) runs in full, and
     its numbers are reported as an observation, "expert = builder". ② stays `untested` until a
     domain with an outside expert runs it. Which milestone that is gets decided when one is
     found.
   - **③ gets a verdict**, from the daily use. The roadmap's brownfield effect through the GitHub
     adapter is replaced by the broker's paper-trading API: placing an order and reading its
     result back.
4. **The declaration starts from the interview.** It does not start from a template or an
   example. It may start from an import of the broker API's specification (A1). Until M2's
   verdicts are frozen, no agent adds a trading example, template or test domain to the
   repository.
5. **Daily use is part of the protocol.** The researcher trades or checks every trading day
   during ③'s window. The days missed are reported.

## Consequences
- M2 can start without recruiting an expert. Recruiting shrinks to the seeder's 1–2 hours, plus
  the newcomer for F2 (ADR-0053), who must be a different person from the seeder.
- The first ② verdict moves past M2.
- ①'s verdict carries a limit that an outside expert's requests would not have.
- ③ is tested on a domain the researcher actually uses, so its defect log reflects real use.
- The paper account bounds the harm: an agent's mistake, or a rule the gate misses, costs no
  money. ③'s finding is then "works as built on a paper account".

## Open questions (decided in M2's spec PR)
1. **Which paper-trading API.** For example, a Korean broker's open API with a paper (모의투자)
   account for Korean stocks, or a US broker's paper account. The choice follows the market the
   researcher trades in.
2. **How the tool reaches the broker.** Recommended: through an MCP server for the broker behind
   `toprope-proxy` (ADR-0052), which exists today. M0b's effect adapters are not built yet.
3. **Who places the order after approval.** Either the agent, through the gated call, or the
   researcher by hand. ③'s brownfield effect needs the gated call.
4. **Who the seeder is.** They must not be Toprope's builder or F2's newcomer. They should know
   enough about investing to read the change requests.
