# ADR-0058: Multiplication in the check language

- Link: ③ works as built (rules a domain owner states as shares), ① iterate safely (TLC checks
  them) · Status: **accepted**, 2026-11-13, decided by SteamShon ("1: 예", to the question
  whether to add it). Drafted by the assistant.
- Extends: the check language (`docs/domain-schema.md`; ADR-0010, ADR-0024).

## Context
In M2's interview the owner stated two limits as shares:
- a sell order's quantity is at most 80 % of the position's;
- a buy order's amount (quantity times price) is at most 50 % of the account's value.

The check language has `+` and `-` only. The first limit can be forced into sums
(`qty+qty+qty+qty+qty <= held+held+held+held`), which no owner would read back as their rule.
The second cannot be written at all: an amount is a product. A rule the language cannot hold is
either dropped or left to the agent's judgement, and either way the gate does not enforce it.

## Decision
1. **`*` on numbers**, binding tighter than `+` and `-`, left to right. Like `-`, it takes numbers
   only. A string, a boolean, null or a list fails closed (`EvalError`).
2. **No division.** Python's `/` gives a float, and TLA+ has only integer `\div`. The interpreter
   and TLC would then disagree on the same rule. A share is written as a product instead:
   `params.qty * 100 <= target.held * 80`.
3. **TLC models it** as an integer product (`OpMul`), next to `OpAdd` and `OpSub`, so the TLA
   cross-check (ADR-0043) covers rules that use it.

## Consequences
- Share limits read as the owner states them, with the percentage written as a whole number.
- Rules over money that is not a whole number still hold in the interpreter. The model checks
  them on its integer sample, as it checks `+` and `-` today.
- M2's checks were frozen at an earlier revision (M2's preregistration). This change is an
  amendment to them, reported with M2's run.
