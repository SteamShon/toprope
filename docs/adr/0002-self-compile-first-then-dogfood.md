# ADR-0002: First domain is Toprope itself (self-compile), then dogfood domains

- Link: ① ② · Status: accepted · 2026-11-04 · decided by: SteamShon

## Decision
M1 models Toprope's own domain-authoring workflow and generates the authoring tool from
that model. This repeats how the original work started. M2 uses that generated tool on a
dogfood domain (candidate: experiment lifecycle).

## Rationale
Authoring is itself a hidden workflow, and the researcher can judge it best. Success gives
every later milestone a generated rather than hand-built authoring tool.

## Consequences
The self domain is biased toward success, because its designer is the researcher, so only
M2 counts as evidence outside it. Circularity and self-approval are guarded by a gold set
and verdict checks kept outside the loop (docs/experiments/M1-self-compile.md).
