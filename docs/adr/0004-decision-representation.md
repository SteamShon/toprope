# ADR-0004 — Decision representation: minimal YAML + PolicyEvaluator port

- Status: accepted · 2026-11-04 · decided by: SteamShon

## Options
**Minimal own YAML + evaluator port** · Cedar/OPA directly · own DSL

## Decision
A small YAML record carries meaning and lifecycle (statement, reason, owner, scope, version,
evidence, exceptions). The `check` block is evaluated through a `PolicyEvaluator` port; the
first adapter is a built-in matcher, with Cedar/OPA as later adapters. See
docs/decision-schema.md.

## Rationale
Existing policy languages have nowhere to put provenance, scope history and exception
accounting — the part this research is about. A full DSL is premature.
