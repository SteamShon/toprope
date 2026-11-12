# ADR-0057: M2's held-out situations may be drafted by an agent that never saw the rules; the researcher judges each one

- Link: ② model is right (what the held-out items observe) · Status: **accepted**, 2026-11-12,
  decided by SteamShon ("이 방식으로 해보자"). Drafted by the assistant.
- Amends:
  - ADR-0056 decision 5: the held-out items' situations, not their answers.
  - AGENTS.md: the human-only rule's exception for M2's held-out items.

## Context
ADR-0056 left the held-out items' questions and answers to the researcher. With the CSV memo
(#270), each item is one row: a situation, and whether the action in it is allowed or denied.
Writing the situations themselves is the hard part. The researcher found that no domain expert
would write twenty open situations, and that the items would then not get written.

Two sources of bias were separated:
- **Bias in the answer.** In an unclear case, an agent answers the way its model family leans. The
  interview's agent leans the same way, so it is scored right even where the researcher would
  decide otherwise. This bias is in the answer, and it is the one that would make ② meaningless.
- **Bias in which situations are asked.** An agent picks situations that its model family finds
  salient, and the interview's agent may ask about the same ones. If the agent that drafts the
  situations never saw the rules, the situations are not steered toward them. This bias is weaker.
  It can be reported.

## Decision
1. **An agent may draft the held-out situations, but only from a session that never saw the
   rules.**
   - The drafting session reads none of the following:
     - `~/m2-private/`;
     - the candidate list (ADR-0056);
     - the transcript of any session that saw the rules.
   - Its brief describes the domain only: who acts, which actions there are, and what amounts and
     times can vary. It does not describe the rules.
   - It writes situations in which an actor tries an action. Amounts and times vary across the
     situations.
   - It writes no answers.
2. **The researcher judges every situation.**
   - The choices are 허용, 거부 or 모름.
   - A situation judged 모름, or left empty, is not an item.
   - The answer is always the researcher's.
3. **Items from these situations are tagged `blind-situation`**, and they are `tacit: true`. The
   researcher judges them from their own rules, which no agent could read.
4. **What M2's report states for ②.**
   - Which items came from blind situations.
   - That an agent chose which situations were asked. That agent never saw the rules.
   - That every answer is the researcher's.
5. **Everything else in ADR-0056 holds.**
   - The answers stay human-only.
   - Items from the candidate list stay tagged `from-list` and are reported apart.

## Consequences
- The researcher's work becomes about one choice per situation. Sixty situations take minutes.
- Rules the researcher never wrote down still show up, because the researcher judges situations
  rather than recalling rules. ② is about exactly these rules.
- The session that saw the rules is not the one that drafts the situations. The researcher deletes
  that session's transcript, or moves it out of the agents' reach, before the interview.
