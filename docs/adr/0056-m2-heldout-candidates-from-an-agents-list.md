# ADR-0056: M2's held-out rules may be picked from an agent's list of published principles, and are labelled

- Link: ② model is right (what the held-out items observe) · Status: **accepted**, 2026-11-12,
  decided by SteamShon ("이 방식으로 하자"). Drafted by the assistant.
- Amends:
  - ADR-0054 §2: the human-only rule, for the held-out items' source rules only.
  - AGENTS.md: "Gold sets are human-only" and its M1 exception.

## Context
M2's held-out items for ② (ADR-0054 §4, `experiments/m2/heldout.template.yaml`) test whether
the model built through the interview gets the researcher's rules right. The researcher writes the
rules first, as a memo (`~/m2-private/rules.txt`), and then turns them into items with
`m2_heldout.py ask --from`. Agents may not read either file.

The researcher has some rules of their own, but not enough. Collecting more from trading books
and portfolio guidelines by hand would take a long time. The researcher asked whether an agent may
read those sources and give a full list with recommendations to choose from.

Two risks were weighed:
- **Contamination across sessions.** No memory carries over, so a later session does not see the
  list.
- **Bias, which a new session does not remove.** A list made by the same model family holds the
  rules that model family finds easy to state. Items built from it are easier for the interview's
  agent to get right, so ② would read higher than the researcher's own rules would make it.

## Decision
1. **An agent may draft a list of candidate rules for the held-out items, when the researcher
   asks.**
   - The list is taken from published sources, and each entry names its source.
   - The agent may mark entries it recommends, judged on whether a trading declaration can
     express them. It does not judge whether they are good investing.
   - The list stays outside the repository and outside `~/m2-private/`.
   - No trading example, template or test domain enters the repository (ADR-0054 §5 is
     unchanged).
2. **The researcher picks, rewrites and decides.**
   - The researcher picks from the list and writes each pick into `rules.txt` in their own
     words, with their own numbers.
   - The agent writes nothing into `~/m2-private/`.
3. **Every item from the list is labelled.**
   - When `ask` asks whether the rule was written down somewhere an agent could read, the
     answer is "있음", so the item gets `tacit: false`.
   - The item carries the tag `from-list` in `covers`.
4. **② is reported in two parts.**
   - Accuracy on items without `from-list`: the researcher's own rules. This is the number ②
     is about.
   - Accuracy on items with `from-list`: reported beside it as a reference only.
   - The report states how many items each part has.
5. **Everything else stays human-only.**
   - The probes, change requests, seeds, key, binding and any gold set for M2 and later.
   - The held-out items' questions and answers. Only the list of candidate rules is affected.

> Amended by ADR-0057: the situations of held-out items may be drafted by an agent session that
> never saw the rules; the researcher judges each one, so the answers stay human-only.

## Consequences
- The researcher saves research time. ② still has a number that rests on rules no agent
  suggested.
- If few of the researcher's own items remain, that part of ② may fall below the 12 items the
  template calls worth reporting. The report then says so.
- The session that drafts the list has seen candidates, not the researcher's picks. Who saw what
  is recorded with M2's report.
