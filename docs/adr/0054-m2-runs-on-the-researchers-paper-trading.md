# ADR-0054: M2 runs on the researcher's own paper trading, with every role the researcher's

- Link: ① iterate safely, ② model is right, ③ works as built (what M2 judges) · Status: **accepted**
  (1–6), 2026-11-11 and 2026-11-12 (market and broker), decided by SteamShon. The researcher chose the domain, a paper-trading
  account and daily use. They chose to take every role, with seeding by a preregistered draw ("이대로
  가자"), and a provisional ① result ("잠정 결과로 해도 될 것 같아"). Drafted by the assistant.
  Open questions are listed below.
- Amends:
  - ADR-0030: ② in M2 needs an expert who is not the builder.
  - ADR-0034 §2: the ① verdict's change requests.
  - `docs/roadmap.md`: M2's domain, its links and its brownfield effect.
  - The README claim-status and milestone tables: where ① and ② are tested. The `Status` column
    is untouched.
  - `docs/experiments/M2-design.md`.

## Context
ADR-0030 and ADR-0034 made M2's ① and ② verdicts depend on a domain expert who is not Toprope's
builder. The roadmap's candidate, the experiment lifecycle, has the researcher as owner, which
fails that condition (ADR-0030, revision 1). No outside person is available, either as an expert
for three to four weeks or as a seeder for an hour or two. The researcher runs no business
domain at the moment.

M2 also judges ③. ③ needs someone to use the generated tool for real, for at least two weeks.
The researcher can do that.

Candidates considered (2026-11-11): the experiment lifecycle, Meta ad operations, a job-search
pipeline, project tracking, and the researcher's own stock investing. Stock investing fits best:

| Need | Stock investing on a paper account |
|---|---|
| The researcher knows the rules | They are the researcher's own investing rules. |
| States and rules to seed problems into | States: idea → research → order proposed → approved → placed → filled, part filled or cancelled → held → sold. Rules: position limits, a cash floor, stop-loss, no buying before earnings. |
| Real use for ③ | Daily trading or checking, on a paper (모의투자) account: real prices, no money at risk. |
| A brownfield effect | The broker's paper-trading API: an order, and its result read back. |
| Not contaminated | Nothing in `examples/` or the templates covers trading. Meta ads would overlap `examples/paid-media`, and project tracking would overlap the self domains. |
| The agent proposes, a person approves | The agent proposes orders, the researcher's rules gate them, and the researcher approves. |

**An agent as the seeder was considered and rejected.** There are three reasons:
- An agent of the family that builds the checks would set the problems the checks are scored on.
  ADR-0034 rejected agent-seeded problems as circular.
- Two of M2's arms are LLM reviews. Problems an LLM seeds may lean toward the problems an LLM
  finds, which would bend the comparison.
- It would need an exception to the human-only rule for a verdict input.

## Decision
1. **M2's domain is the researcher's own stock investing, on a paper-trading account.** The
   researcher is the expert, the owner, the seeder and the user. What the domain contains
   (states, actions, rules, outcome rules) comes from the researcher's interview, not from this
   ADR. No live brokerage account is connected in M2.
   - **Market and broker (decided 2026-11-12, "미국으로 가자").** M2 covers US stocks only, on an
     Alpaca paper-trading account. The researcher invests in both Korean and US stocks. One
     market keeps the API surface to one, and the rules can be written so they do not depend on
     the market.
   - **How the tool reaches the broker.** Through Alpaca's official MCP server
     (`alpaca-mcp-server`), behind `toprope-proxy` (ADR-0052). That server defaults to paper
     trading, and M2 never sets it to live.
   - **Why not a Korean broker.** No official MCP server was found for a Korean broker's paper
     account, only community ones. Their defects would mix into ③'s defect log.
   - **The time difference.** US trading hours fall in the Korean night. An order proposed and
     approved in the day waits for the open, and its fill is read back the next morning.
2. **The human-only rule is unchanged.** M2's change requests, seeds, key, probes, binding and any
   gold set are written by the researcher. An agent drafts none of their content.
3. **The researcher does not choose which problems to seed.** The bias ADR-0034 named comes from a
   person who knows what the checks catch choosing the problems. The isolation protocol below
   removes that choice. Each step is preregistered in M2's spec PR.
   1. **The checks are frozen first.** The Toprope revision that runs M2's checks is recorded
      before any problem is written. A change to the checks after that is an amendment, reported
      with the run.
   2. **The change requests come from real use.** During the daily use, the researcher keeps a
      diary of the rule changes they actually want. The change requests are taken from it in
      order. None is picked or reworded for how testable it is.
   3. **A draw decides the seeds.**
      - The problem types are preregistered: conflicts with a rule, breaks a reference, widens
        who can act, breaks an outcome rule, and none (a clean control).
      - Each type has a share.
      - For each request, a hash of the request text and a salt decides whether it is seeded and
        with which type. The salt's hash is committed before the draw, and the salt is revealed
        after the run.
      - The researcher writes the problem of the drawn type into the request.
   4. **What the draw does not remove.** How a drawn problem is written into a request (how
      plain or how subtle) is still the researcher's. That limit is reported with ①.
   5. **The key is sealed.** Its hash is frozen in `FROZEN.json`. The key itself stays outside
      the repository until every arm has run every change. As in M1, only the scorer opens it.
      No agent sees the requests or the key before the run.
4. **What M2 reports.**
   - **① is a provisional result.** It is computed by the frozen verdict rules and reported in
     M2's report with its limit: one person was expert, requester and seeder, and the seeds
     were drawn. The claim-status table keeps ① `untested`. A run whose problems are seeded by
     someone who is not the builder can confirm it later.
   - **② is an observation.** The held-out protocol (ADR-0030, decision 2) runs in full, and its
     numbers are reported with the label "expert = builder". ② stays `untested` until a domain
     with an outside expert runs it.
   - **③ gets a verdict**, from the daily use. The roadmap's brownfield effect through the
     GitHub adapter is replaced by the broker's paper-trading API: an order is placed, and its
     result is read back.
5. **The declaration starts from the interview.** It does not start from a template or an
   example. It may start from an import of the broker API's specification (A1). No agent adds a
   trading example, template or test domain to the repository until M2's results are frozen.
6. **Daily use is part of the protocol.** The researcher trades or checks every trading day
   during ③'s window. The days missed are reported.

## Consequences
- M2 needs nobody else. F2's newcomer (ADR-0053) is still a separate need.
- The first ① and ② verdicts move past M2. M2 gives a provisional ①, an observed ② and a ③
  verdict.
- The isolation protocol costs one preregistration step (the types, shares and salt hash) and a
  diary kept during the daily use.
- ③ is tested on a domain the researcher actually uses, so its defect log reflects real use.
- The paper account bounds the harm: an agent's mistake, or a rule the gate misses, costs no
  money. ③'s finding reads "works as built on a paper account".

## Open questions (decided in M2's spec PR)
Which paper-trading API to use, and how the tool reaches it, are decided in decision 1.

1. **Who places an approved order.** Decided 2026-11-12 ("추천대로"): the agent places it,
   through the gated call ([`M2-spec.md`](../experiments/M2-spec.md) §1).
2. **The draw.** This covers the problem types' shares, the share of clean controls, and how
   many change requests there are. M1 had about 20. Drafted in `M2-spec.md` §5.
3. **Enough change requests.** Two weeks of a diary may hold fewer requests than Phase B needs.
   Drafted in `M2-spec.md` §4–5.
4. **Whether M2 waits for M0b.** Drafted in `M2-spec.md` §6. The roadmap puts M0b first. M2's brownfield effect no longer
   needs M0b's GitHub adapter, but ③'s live changes call for migration plans (ADR-0018), which
   are an M0b item.
5. **Paper only, enforced.** The rule that M2 never trades live needs a check, not only this
   text. Drafted in `M2-spec.md` §1.
