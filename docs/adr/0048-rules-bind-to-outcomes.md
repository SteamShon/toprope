# ADR-0048: Rules bind to outcomes, and the change check diffs who can reach them

- Link: ① iterate safely, ③ works as built · Status: accepted · 2026-11-08 · decided by:
  SteamShon ("in the recommended order, go"; drafted by the assistant)
- Builds on: [M1-report.md](../experiments/M1-report.md) (*Why the Toprope arm missed rule
  conflicts*, *What M2 takes from this* 1–2), ADR-0009 (natural-language checks), ADR-0010
  (matrix, invariants, harness), ADR-0016 (actors and agents)

## Context
In M1 the compiler missed most changes that conflict with a rule. Change 3 is the clearest case.
"Only a person confirms an element" was written as `requires: human` on `confirm_element`. The
editor added a new action that an agent may take, and that action also leads to `confirmed`. The
new declaration is consistent, so every check passed. The rule was bound to one action, and a new
action went around it.

Invariants cannot say this rule. An invariant is a predicate on state, and who did something is
not state unless the declaration chose to record it. The matrix and `requires` are per action.
Nothing in a declaration says "whatever the action, only a person may bring this about".

## Decision
1. **Outcome rules.** A declaration may list `rules`, each about an outcome:
   ```yaml
   rules:
     only-a-person-confirms:
       on: Element.confirmed            # <Object>.<state>, or <Object>.<property> for a set
       requires: human                  # or {roles: [...]}, or {check: <expression>}
       reason: Only a person confirms an element.
   ```
   - `on: Object.state` covers every action whose matrix cell moves an `Object` into that state.
     `on: Object.property` covers every action whose effects set that property.
   - `requires` takes the forms an action already has: `human`, roles, or a check-language
     expression over `actor`, `target` and `params`.
   - Each rule carries `source` and `status` like any element.
2. **Enforced on every path.** The interpreter checks a rule with the action's own preconditions.
   The denial gives the rule's id and reason. Every action that reaches the outcome is held to the
   rule, including one added later. The validator lists the actions each rule covers. The harness
   tests each covered cell with an actor that the rule refuses.
3. **A capability diff in the change check.** The change check computes, before and after the
   change, who can reach each outcome. For every object state and every set property, it records
   the actions that reach it, the actor kinds and roles that may take each action, whether
   `requires: human` applies, and the preconditions and rules on the way. Then it compares the two.
   - A widening is a **warning**, naming the outcome, the new path and what it drops. A widening
     is a new action, a new role or actor kind, a dropped `requires: human`, or a dropped
     precondition or rule.
   - A narrowing is **info**.
   - The diff runs whether or not the domain declares rules. With rules, a change that widens
     what a rule guards fails the harness as well.
4. **The interview asks for outcome rules.** At the stage for invariants, the interview also asks
   what may never happen, whatever the action, and by whom. The answers are proposed as rules.
5. **The self domains adopt them** in their own reviewed changes. Their person-only rules become
   outcome rules: an element confirmed, a commit approved, a decision recorded, a deploy. These are
   proposed by an agent and confirmed by the researcher, through the usual loop.
6. **Judged in M2, not by M1's data.** The assistant that writes these checks has seen M1's key.
   So any number they produce on M1's change list is biased, and serves only to show that the
   checks run. Their effect is measured in M2, on a change list someone else writes.

## Consequences
- The schema grows by one element kind (`rules`), with its JSON Schema, validator, interpreter,
  harness, TLA+ export (as a guard on the transitions it covers) and generated guide.
- The capability diff touches no declaration. It is a check over two declarations, so existing
  domains get it at once.
- A rule written as `requires: human` on one action still works. The validator suggests an
  outcome rule when every action reaching a state requires a person.
