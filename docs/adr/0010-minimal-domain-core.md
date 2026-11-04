# ADR-0010: Minimal domain core: Object, Link, Action

- Status: accepted · 2026-11-04 · decided by: SteamShon
- Supersedes: ADR-0004

## Options
**Minimal core** · prior Toprope's full set (Object/Link/Action/Policy/Contract/Flow) · an external schema language (LinkML, JSON Schema) plus actions

## Decision
Start with Object, Link and Action (params, preconditions with reasons, effects, actor
roles, `records_decision`). Policy, Contract and Flow are added only when a concrete task
needs them, each with its own ADR naming that task. Reusing LinkML or JSON Schema for
objects will be revisited after M0. See docs/domain-schema.md.
