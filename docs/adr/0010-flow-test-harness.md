# ADR-0010: The compiler generates a flow test harness from the declared scenarios

- Link: ① iterate safely, ③ shared language · Status: accepted · 2026-11-04 · decided by: SteamShon

## Context
ADR-0009's scenario regression evaluates scenarios against the **model**. That shows the
declaration still means what it meant. It does not show that the **generated code** works:
the MCP server, the A2UI views, Execution with its state store, and the adapters. Code that
was generated but never exercised is not known to work. Every rebuild (and P0 says there
will be many) can break a generated surface without changing the model at all.

## Decision

### 1. Scenarios become flows
Scenarios in the domain can be multi-step **flows**. A flow has a starting state, then
ordered steps, each with an actor, an action or a read, and expectations. Expectations can
check state, a denial with its precondition and reason, a recorded decision, the
actions currently allowed, and what a declared view shows. Single-step scenarios (ADR-0009)
are flows of length one.

### 2. The compiler generates one harness per surface from the same flows

| Level | What runs the flow | What it proves |
|---|---|---|
| Model | the reference interpreter of the declaration | the declaration means what the flow says (ADR-0009 regression) |
| Execution | Execution with the real state store and event log | preconditions, roles, effects and decision records work in the runtime |
| MCP | an MCP client calling the generated server in the preview environment | tools exist, params validate, denials carry the declared reason, state changes match |
| UI | the compiled A2UI views for the resulting states | declared views show exactly the allowed actions and the declared fields; forms submit the same action and get the same outcome |
| Adapter | each `EffectAdapter` against fakes or a sandbox, with read-back | effects happen as declared; timeouts surface as `UNKNOWN`, never as success |

### 3. Parity across surfaces
The same flow must produce the same outcome at every level. Any disagreement, such as the
model allowing something the MCP rejects, or a view showing an action Execution would deny,
is a **parity failure**. This is the mechanical check behind ③: people (UI) and agents
(MCP) see the same actions and the same rules.

### 4. Coverage gaps are reported
The harness reports actions, preconditions, state transitions and declared views that no
flow exercises. An uncovered element is a warning in the change check, and it prompts the
author to add an example. This is where most missing examples will be found.

### 5. Where it runs
The harness is part of the change-check pipeline. It runs on every rebuild against the
preview build. A failing flow or parity failure blocks deployment of that build. A
representation-only change runs only the UI-level harness, plus parity on the affected views.

### 6. What it does not prove
The harness is generated from the same declaration as the code, so it verifies that the
code **conforms to the declaration**. It cannot show that the declaration is **right**. That
remains the job of the held-out gold scenarios, the post-deploy probes, and people (②).
Held-out gold flows are never part of the domain, so they are never in the generated harness.

## Consequences
- Harness generation is a compiler output alongside MCP, A2UI views and the interface.
- UI-level checks start at the A2UI message level (deterministic, cheap). Browser end-to-end
  tests are added only for host-injected components, which the compiler cannot inspect
  (ADR-0008).
- M0 generates the harness for the model, Execution and MCP levels, plus A2UI message-level
  UI checks. Adapter-level checks begin with the first real `EffectAdapter`.
