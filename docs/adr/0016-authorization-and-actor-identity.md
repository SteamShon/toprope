# ADR-0016: Authorization and actor identity, including agents

- Link: ③ works as built, ④ shared language · Status: accepted · 2026-11-04 · decided by: SteamShon
- Origin: design review 2026-11-04 (finding 3)

## Context
Roles alone are not enough. Real rules depend on relationships ("the experiment's owner"),
on delegation, and on agents acting for people. A correctness layer that cannot say who may
act is incomplete.

## Decision
1. **Actors** are `person`, `agent` or `system` (including `external:<source>`, ADR-0015).
   Identity comes from the host through an `Identity` port (OIDC/JWT first). Toprope does not
   manage accounts.
2. **Relationship-based permissions.** An action's actor rule may combine a role with a
   relation, e.g. `actor: {role: pm, where: "actor.id == target.owner"}`. Relations use the
   same `check` language.
3. **Agents act on behalf of a principal.**
   - Every agent call carries `on_behalf_of` (a person) and a **grant**: the actions,
     targets, expiry and budget allowed.
   - An agent can never do more than both its own role and its principal allow.
   - Actions marked `requires: human` can never be performed by an agent.
   - Confirming domain elements is one such action, which is the no-self-approval rule.
4. **Recorded.** Every event records the actor, `on_behalf_of` and the grant id
   (ADR-0012).
5. **Tested.** The harness's role dimension includes relations and agent grants. Cell tests
   run for a person, for an agent with a grant, and for an agent without one.

## Consequences
- The small world gains actors with relations (owners, teams) and agents with grants.
- The generated MCP refuses calls without identity. It returns the denial reason in
  domain terms, as for any other denial.
