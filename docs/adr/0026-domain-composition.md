# ADR-0026: Domains compose; a composition file declares how

- Link: ④ shared language, ⑥ org productivity, ① iterate safely · Status: **proposed**
  (assistant draft, from the researcher's preference for composition over inheritance) ·
  2026-11-04
- Builds on: ADR-0008 (domain interface), ADR-0022 (two self domains and a handoff), ADR-0024
  (handoff outbox)

## Context
- Organizations run many workflows that hand work to each other. Toprope already joins
  domains without inheritance:
  - a sender declares `handoffs` into another domain's published interface
  - `check_handoffs` checks the contract at compile time
  - the world map marks edges that hand off
- Which domains make up a system, and how they are wired, is still declared nowhere. Three
  gaps follow:
  1. **The wiring is not declared.** The receiving domains and their interface majors are
     passed on a command line (`toprope-harness --receiver`), so nothing records that
     "this system is Authoring v3 and Delivery v2, joined by `deliver`".
  2. **A receiver cannot choose its senders.** A receiving action that allows `system`
     accepts a handoff from any domain wired to it.
  3. **Paths stop at domain boundaries.** The world map and `how_to_reach` stop at the
     boundary, so "from a drafted version to a deployed build, who acts at each step?" has
     no answer.

  M1 needs the third to grade facts that span the boundary.

## Decision
1. **Composition, never inheritance.** A domain never extends or overrides another. It
   connects only through another domain's published interface, today by handoffs and later
   by read-only queries. Shared vocabulary is shared by glossary terms and aliases
   (ADR-0008), not by shared objects.
2. **A composition file** (`*.composition.yaml`) declares a system:
   ```yaml
   composition: toprope-self
   version: 1
   members:
     authoring: {declaration: authoring.domain.yaml, interface: 1}   # published major
     delivery:  {declaration: delivery.domain.yaml,  interface: 1}
   wiring:
     - {from: authoring.deliver, to: delivery.request_delivery}     # sender handoff → receiving action
   ```
   Compiling it checks four things:
   - every member validates
   - every handoff declared by a member is wired, and every wire names a declared handoff
   - every wire passes `check_handoffs` against the member's published major
   - no domain appears twice

   A released system is the tuple of its members' versions.
3. **Receivers accept only wired senders.** The receiving Execution learns the sender
   domain and handoff of each command, and records them on its events (the handoff id
   already links the two stores). It refuses a handoff that the composition does not wire
   to that action, before evaluation, as `denied: actor`. A domain served alone (no
   composition) keeps today's behavior.
4. **A composed world map.** The members' maps are joined. Each wire becomes an edge from
   the sender's handing-off edges to the receiver's action. `how_to_reach` can then answer
   across domains: the path continues in the receiving domain once the handoff fires.
5. **Grading across the boundary.** A gold fact about one domain is graded against that
   domain's compiled model. A fact that spans the boundary (for example, what the receiver
   gets when the sender approves) is graded against the composed model. This keeps the
   researcher's rule that every item must be answerable from a declaration.

## Consequences
- M0a adds the composition file, its compile-time check, the receiver's allowlist and the
  composed world map. This is a small item: it reuses `check_handoffs` and `build_world_map`.
- `toprope-harness --receiver` is kept for a single sender; `--composition` supersedes it.
- The M1 self domains get a composition file in Phase A. The wiring follows the confirmed
  handoff contract in the scope document.
- Later: read-only cross-domain queries as a second kind of connection, with their own ADR.
