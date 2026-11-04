# ADR-0003 — M1 tests H-Enforce before H-Author

- Status: **superseded by [ADR-0009](0009-m1-shared-language.md)** · 2026-11-04 · decided by: SteamShon

## Decision
The first experiment compares a pre-tool gate with `CLAUDE.md` prose (see
docs/experiments/M1-enforce.md). It is cheaper to measure (violation rate), faster to
falsify, and builds the substrate authoring results will feed.

## Kill/pivot
If prose ≈ gate within noise, enforcement is repositioned as a safety boundary for
irreversible actions and research weight moves to authoring (M2).
