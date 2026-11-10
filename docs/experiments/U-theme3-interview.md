# Theme 3: the interview and its feedback (ADR-0049)

Link: ② model is right (indirectly: the interview is how an expert's knowledge gets in), and ⑥.
The plan for `umbrella/usability-interview`, stacked on theme 1 (`umbrella/usability-change-loop`,
#201). It merges into `develop` after theme 1, once M1's recheck is in. Progress is in
[`STATUS.md`](../STATUS.md).

**What this umbrella does not do.** It changes the interview services and the reports (code in
`src/toprope/workspace` and `src/toprope/check`). It does not change the self domains'
declarations or run their loop: adopting the new question forms in Authoring's own declaration
waits until M1's recheck is done (AGENTS.md, one loop at a time).

## Targets

| Measure | Today | Target |
|---|---|---|
| interview questions that offer choices with a recommended answer | 0% | 80% or more of those asked in F2's interview |
| impact report | lists cells and element keys | states the decisions a person must make, in the domain's words |
| a counterexample | a trace of states and actions | a short story in the domain's terms, with the rule it breaks |

## Sub-PRs, in order

| # | Item |
|---|---|
| 1 | B1: questions offer choices, each with the decisions it makes, and one recommended with its reason (fail-closed where nothing else suggests an answer); answering by choice applies them |
| 2 | B2: ask for examples first: the interview asks for a few real cases before the rule, and turns each into a fixture or scenario proposal |
| 3 | D2: the impact report as decisions: "Approve this, and support may refund on day 30" rather than cell counts |
| 4 | D3: counterexamples as stories, in the glossary's terms |
| 5 | B3: a live map of the domain while answering: the world map (`toprope-worldmap`) rendered for the current draft after each answer |

## Done when
Every row is done, and F2's interview (measured by an operator the researcher finds) meets the
80% target.
