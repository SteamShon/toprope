# ADR-0037: Switch-over: the generated self domains replace the hand-built tools

- Link: self-compile (feasibility), ③ works as built · Status: **proposed** · 2026-11-06 · direction
  decided by the researcher; the plan and the open choices are the assistant's draft
- Builds on: ADR-0022 (the switch-over), ADR-0027 (what the kernel is), ADR-0028 (kernel
  services as declared effects), ADR-0036 (generated command line and guide)

## Context
The researcher set the switch-over's done criterion: **every hand-built tool goes, replaced by
tools generated from the declarations, so that almost nothing in the project is hand-built.**

What is hand-built today (about 9,000 lines of `src/`):
- **The kernel** (ADR-0027): expression language, declaration models and validator,
  interpreter, Execution, event stores, identity, the generators (MCP server, command line,
  world map, guide), harness, change check and incremental analysis, the commit store, the
  deploy floor, kernel services, composition. This is the compiler and runtime that turns a
  declaration into working software. It cannot be generated from a declaration without a
  declaration language for compilers; it stays hand-built and is kept small.
- **Hand-built self-domain tools** (not kernel, ADR-0027 §2), about 1,700 lines:
  - `toprope-author`: the interview workspace (stages, questions, propose with provenance,
    answer, confirm, skip), commits, checks, approve, merge, log, checkout, ship
  - `toprope-deploy`: preview, deploy, status
  - their hand-written guides (`docs/authoring.md`, the Authoring and Delivery sections of
    `docs/workflow.md`)

## Decision (proposed)
1. **The line.** After the switch-over, the only hand-built code is the kernel. Every tool a
   person or an agent uses to author or deliver a domain is generated from `domains/*.domain.yaml`:
   the MCP servers and `toprope-run` (ADR-0036), and its documentation is the generated guides.
2. **What the domain tools do becomes kernel services or declared actions.**
   - Operations on a working copy that every domain's authoring needs (write a proposed
     element with its provenance, confirm one, plan a stage's questions, read and search
     sources, record an answer) become **kernel services** (ADR-0028), like `commit` and
     `change_check` already are. They are generic: they operate on any declaration.
   - Everything else, who may do what and when, is already **declared** (Phase A): the Authoring
     and Delivery actions, the matrix, `requires: human`, the handoff.
3. **The order**, one sub-PR each (an umbrella, `umbrella/switch-over`):
   1. kernel services for the interview: `propose_element`, `confirm_element`, `answer`,
      `stage_questions`, `search_sources`, `skip_stage`
   2. the Authoring declaration calls them (actions and replies added through a normal change:
      commit, change check, confirm, approve)
   3. a local identity so a person can run `toprope-run` as themself (see Open, 2)
   4. run the whole loop on the generated tools: interview → commit → check → approve → deliver →
      preview → deploy → verify, end to end, and the regeneration check (ADR-0028)
   5. remove `toprope-author` and `toprope-deploy`, their modules and their hand-written guides;
      `docs/workflow.md` keeps only the kernel's commands and points to the generated guides
4. **Done when** (the researcher's criterion, made checkable):
   - no hand-built Authoring or Delivery code is left: `src/toprope/authoring/` and
     `src/toprope/deploy/cli.py` are gone, and what they did is a kernel service or a declared action
   - the self domains run end to end from their declarations alone, on the generated surfaces,
     with the regeneration check passing and zero hand edits to generated code
   - every guide for authoring and delivering is generated
   - the researcher signs off (ADR-0022)

## Consequences
- M1's self-compile result can be reported as "nothing but the kernel is hand-built".
- The kernel grows by the interview services, which are generic and tested like the rest.
- People and agents use `toprope-run` / the MCP servers for the self domains from then on.

## Open (for the researcher)
1. **Where the self domains' runtime state lives.** Answers, confirmations and requests are
   events in the generated domains' event stores. Options: commit an append-only event log to
   git (like the commit store), or keep a local SQLite store and commit only the declarations
   and the commit store.
2. **How a person is identified on the command line.** Options: a local identity that maps
   your git identity to roles listed in the repository (e.g. `toprope.identity.yaml`), or a
   token file as for the server.
3. **The kernel's own guide.** Keep `docs/workflow.md` (kernel commands only), or generate it
   from the kernel's command definitions too.
