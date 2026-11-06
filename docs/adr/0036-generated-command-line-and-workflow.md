# ADR-0036: A command line and a how-to-work guide, generated from the declaration

- Link: ③ works as built, ④ shared language · Status: accepted · 2026-11-06 · decided by:
  SteamShon (answer 27A; drafted by the assistant)
- Builds on: ADR-0028 (domains generated end to end), ADR-0027 (what the kernel is)

## Context
`docs/workflow.md` and `docs/authoring.md` were written by hand, and so were the
`toprope-author` and `toprope-deploy` commands they describe. The researcher pointed out that
a command line is code too: for a declared domain it should be generated like the MCP server,
and its "who does what, when" should come out of the self-compile, not be a separate document.

## Decision
1. **A generated command line**, `toprope-run`, for any declaration or member of a
   composition: one subcommand per action, with typed options from the params and the
   declaration's own words as help, plus `get`, `history`, `allowed` and `guide`. It runs
   through the same Execution as the MCP server, so the same rules hold: matrix, actor rules,
   preconditions, invariants, `requires: human`, kernel effects and handoffs.
2. **The domain guide says who does what, when** (`## How to work in this domain`): for each
   tracked thing, how it comes to exist, then each stage in the order things move through
   them, with every action allowed there, who takes it (a role, the kernel's reply, another
   domain's handoff), whether only a person may, what it needs first, what it starts, and the
   command to run it.
3. **Hand-written guides keep only the kernel.** The harness, the world map, the instrument
   tool, the deploy floor and releases are the kernel (ADR-0027); their guide stays written.
   Until the M1 switch-over, the bootstrap commands for Authoring and Delivery
   (`toprope-author`, `toprope-deploy`) stay documented in `docs/workflow.md`; after it, those
   sections are replaced by the self domains' generated guides.

## Consequences
- Every declared domain gets a command line and a working guide with no extra writing.
- The generated guides of the self domains (`domains/*.guide.md`) are the documentation of
  Authoring and Delivery as declared.
