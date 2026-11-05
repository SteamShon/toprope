# ADR-0011: Toprope as correctness layer and software factory; link ③ "works as built"; greenfield and brownfield from M0

- Link: ③ works as built (new), all (chain v3) · Status: accepted · 2026-11-04 · decided by: SteamShon
- Supersedes: the chain definition in ADR-0009. ADR-0009's change-safety decisions stand.

## Context
The researcher's experience from building with DDD and coding agents is this: once the
domain is well defined, with a transition matrix and invariants, and the harness passes,
generated code has had almost no problems in production. The harness checks every allowed
and denied state, not a call graph. So writing the code is nearly free, and the value lies
in the declaration and the harness.

This is what makes Toprope a **software factory**. For each new internal tool, external tool
or consumer product, there is no development project. A person who is not a developer
defines the world model through the interview, and the output is software that person can
actually use.

On its own, the correctness layer has little meaning. It sits between:
- an **intelligence layer**: agents such as Claude Code or Codex, and people, who perceive
  the world model and its allowed boundary
- an **effect layer**: a greenfield backend, or existing servers with real effects.

## Decision

### 1. Three layers
- **Intelligence**: agents and people. They see the world model through the generated MCP,
  the UI and the domain interface, and they propose actions.
- **Toprope (correctness layer)**: declaration, transition matrix, invariants, Execution
  gate, event log, and harness-verified generated surfaces.
- **Effects**:
  - *greenfield*: Toprope generates the backend (a domain API over its event store and
    projections, which are the system of record; ADR-0012)
  - *brownfield*: existing servers, APIs and databases behind `EffectAdapter`s, with
    read-back and `UNKNOWN` outcomes.

### 2. Chain v3: a new link ③
```
P0 → ① iterate safely → ② model is right → ③ works as built → ④ shared language → ⑤ evolves → ⑥ org productivity
```
- **③ works as built (H-Factory)**: software generated from a harness-passing declaration
  works in real use, with no state-permission defects and no hand edits to generated code.
  Other defect classes (UX, performance, external API quirks) are counted separately.
  Verdict: M2, from dogfood use of harness-passing builds (both greenfield and brownfield).
- The former ③ shared language, ④ evolves and ⑤ org productivity become ④, ⑤ and ⑥. Link
  labels in existing documents and ADRs were renumbered mechanically. No decision changed.

### 3. Greenfield and brownfield from M0
- **Greenfield**: the compiler also generates a backend, a domain API over the event store and
  its projections (ADR-0012), so a declared domain is usable software without any other system.
- **Brownfield**: one adapter to a real external HTTP API, with read-back and `UNKNOWN`
  handling. GitHub (issues and labels) is the candidate: it is real, free and easy to
  observe. The harness runs adapter-level checks against it (a sandbox repository).

### 4. Hosting topology: open (decided later by ADR-0017)
How the correctness layer is deployed is not decided. Candidates:
- (a) a **gateway / sidecar** in front of brownfield effect servers: agents → Toprope MCP →
  adapter → server
- (b) **embedded** in the generated greenfield backend, as a library in the same process
- (c) a **hosted service** for many teams. This remains a non-goal for now.

The same Execution core should serve (a) and (b). M0 builds both shapes on the toy domain
and records what each costs, and the decision follows in its own ADR.

## Consequences
- M0 grows: greenfield backend generation, plus one brownfield adapter with adapter-level
  harness checks. (Its estimate was later revised to 6–8 weeks, split into M0a and M0b, after
  ADR-0012 and ADR-0013 added more kernel scope; see the roadmap.)
- M2 gives verdicts on ③ in addition to ① and ②. Dogfood use logs every defect found in
  harness-passing builds, with its class.
- Evidence level: the "nearly free" claim is *observed, not measured* until M2.
