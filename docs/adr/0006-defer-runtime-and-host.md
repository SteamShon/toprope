# ADR-0006: Defer runtime and host choices

- Link: none · Status: accepted · 2026-11-04 · decided by: SteamShon

## Decision
No durable runtime (Temporal, LangGraph) or host (OpenDots) is adopted while actions are
short-lived calls against a local store. They stay candidates behind the `EffectAdapter`
and `HumanSurface` ports. OpenDots needs CopilotKit Intelligence for conversations, so it
is not assumed to be a free drop-in.
