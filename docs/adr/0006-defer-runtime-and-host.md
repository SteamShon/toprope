# ADR-0006 — Defer runtime and host choices

- Status: accepted · 2026-11-04 · proposed by: assistant, accepted by: SteamShon

## Decision
While actions are short-lived calls against a local store, no durable runtime (Temporal, LangGraph) or host
(OpenDots) is adopted. They stay candidates behind the `EffectAdapter` and `HumanSurface`
ports. Re-open when a milestone needs durable multi-step workflows or a shared UI.

## Notes
OpenDots requires CopilotKit Intelligence for conversations (hosted, local Docker eval, or
licensed self-host); it is not assumed to be a free drop-in host.
