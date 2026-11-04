# ADR-0001 — Scope: enforcement + authoring

- Status: **superseded by [ADR-0007](0007-reframe-org-workflow-as-domain.md)** · 2026-11-04 · decided by: SteamShon (grilling session)
- Evidence: notes/ko/2026-11-04-grilling.md

## Context
Prior work spans three threads: (A) enforcing approved decisions on the execution path,
(B) the knowledge/decision authoring lifecycle for serious agent users, (C) learning response
models from decisions and outcomes. Evening time cannot carry all three.

## Options
A only · B only · **A+B** · A+B+C

## Decision
A+B, as one loop: decisions are authored from work history (B) and hold on the execution
path (A). C is deferred: it needs traffic and outcome data a personal project lacks.

## Consequences
Enforcement is built first (ADR-0003) so authoring has somewhere to land.
