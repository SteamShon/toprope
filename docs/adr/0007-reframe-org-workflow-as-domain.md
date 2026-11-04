# ADR-0007: Reframe: organizational workflows as domains, not agent guardrails

- Status: accepted · 2026-11-04 · decided by: SteamShon
- Supersedes: ADR-0001
- Evidence: notes/ko/2026-11-04-reframe.md (researcher's correction)

## Context
Charter v0.1 framed Toprope as enforcing decisions on an agent's execution path and compared
a hook gate with `CLAUDE.md`. The researcher corrected this: Toprope was never mainly about
agent safety. The motivating problem is that individual productivity rose while
organizational productivity did not, because the workflows between people (code → product,
hypothesis → experiment → metric → decision) are implicit and oral, and decisions do not
accumulate.

## Decision
The research centers on modeling workflows as domains (objects, links, actions, as with an
ontology plus action types). The model is compiled into a capsule that generates both MCP
(agents) and UI (people), so both share one language. An author-in-the-loop factory turns
run logs into agent proposals and human decisions. Enforcement remains a property of the
model, not the goal. Thread C (learning) stays deferred; the accumulated decision log is its
future dataset.
