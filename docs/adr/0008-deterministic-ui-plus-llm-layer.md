# ADR-0008: Deterministic base UI plus an LLM explanation layer

- Link: ③ shared language · Status: accepted · 2026-11-04 · decided by: SteamShon

## Context
The intent was "declaration → generated UI", in the style of OpenUI and CopilotKit.
OpenUI (thesysdev, MIT) declares a component library, but an LLM chooses the screen at
runtime, so the same domain can render differently each time. A2UI (Google, Apache-2.0,
public preview, supported by CopilotKit) is a pure-data component format. It can be
emitted from a domain model with no LLM.

## Decision
- **Base surface: deterministic.** Lists, details and action forms are generated from the
  domain model (A2UI fixed schema, or our own generator emitting it). The actions,
  parameters, preconditions, reasons and glossary terms always match the generated MCP.
- **Explanation layer: LLM-generated.** Views such as "why is this blocked?", summaries and
  exploratory dashboards may use generative UI (OpenUI or CopilotKit generative modes) over
  the same data. They never introduce actions that the base surface lacks.

## Rationale
③ requires people and agents to see the same actions and rules. A surface that varies
per run cannot be the shared reference. It can explain, but not define.
