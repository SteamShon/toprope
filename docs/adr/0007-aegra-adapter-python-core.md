# ADR-0007: Python core; Aegra as the runtime adapter; TypeScript frontend

- Link: ① ⑤ (authoring agents, proposal loop) · Status: accepted · 2026-11-04 · decided by: SteamShon
- Supersedes: ADR-0006

## Context
The researcher wanted to build on Aegra (https://github.com/aegra/aegra), a self-hosted,
Apache-2.0 replacement for LangGraph Platform. It is built on Python 3.12, FastAPI,
LangGraph, PostgreSQL and Redis. It provides assistants, threads, runs, human-in-the-loop
interrupts, SSE streaming, cron, auth and OpenTelemetry. Custom graphs are registered in
`aegra.json`, and custom FastAPI apps are mounted with `http.app`. It does **not** expose
MCP servers. Its README lists AG-UI/CopilotKit and Agent Chat UI as compatible (not
independently verified).

## Decision
- **Domain core in pure Python.** The model, compiler, precondition/role execution and event
  log never import Aegra or LangGraph.
- **Aegra hosts the agent workflows** (drafter, interviewer, proposal engine): long-lived
  threads, interviews as HITL interrupts, periodic proposal mining as cron. Aegra sits
  behind a `Runtime` port.
- **Generated MCP and domain API** are mounted as custom routes on the same server, if the
  spike confirms this works, including auth.
- **Frontend in TypeScript** (React + CopilotKit over AG-UI).
- Python tooling: `uv`. Analysis is also in Python.

## Consequences
- M0 starts with a 1–2 day spike: Aegra running a toy graph, an MCP server mounted on custom
  routes (with auth checked, since Aegra's route auth covers FastAPI routes but not plain
  Starlette mounts), CopilotKit connected, and one A2UI form rendered.
- Risk: Aegra's maturity (about 1.3k stars, many open issues, no confirmed release version
  seen). It stays an adapter, replaceable by LangGraph Platform or another runtime.
- Option for later: the compiler could also emit LangGraph graphs for domain flows.
  Not decided.
