# Theme 4: import and wrap (ADR-0049)

Link: ② model is right (a declaration starts from what a team already wrote down), ③ works as
built (rules over the tools agents already call), ⑥. The plan for `umbrella/usability-import`,
stacked on theme 1 (`umbrella/usability-change-loop`, #201); it merges into `develop` after
theme 1, once M1's recheck is in. Progress is in [`STATUS.md`](../STATUS.md).

A team already has its rules somewhere: an `AGENTS.md` or skill files, an OpenAPI spec, enums in
a database, a ticket workflow, MCP servers its agents call. This theme starts a declaration from
those, and puts rules in front of those servers.

## Targets

| Measure | Today | Target |
|---|---|---|
| a draft from an existing source | none: the interview starts from nothing | a proposed draft, with a source on every element, from each of: OpenAPI, SQL enums, a ticket workflow export, `AGENTS.md`/skill files |
| conflicts in the source | not found | listed, each with both places, before anything is proposed |
| an existing MCP server under rules | not possible | its tools called through the gate (A2, after ADR-0052) |

## Sub-PRs, in order

| # | Item | Notes |
|---|---|---|
| 1 | A1a, through the ports of ADR-0051 (a Reader, an Extractor, a profile; plugged in through entry points): extractors that need no model: OpenAPI (operations → actions with typed params, enum schemas → states), SQL `CREATE TYPE … AS ENUM` / `CHECK … IN (…)` → enum properties, a ticket workflow export (states and transitions) → a transition matrix. Each writes proposed elements citing the exact place they came from | deterministic |
| 2 | A1b, as the `rules` extractor with a `tree` reader for folders: `AGENTS.md` and skill files → candidate rules and a conflict list: sentences with must / never / only / cannot / before are extracted with their place, contradictions (the same subject, opposite modality) are listed; the candidates are questions for the interview, never rules by themselves | deterministic extraction; the agent drafts the elements from them |
| 3 | ADR-0052: rules in front of an existing MCP server (A2) | the researcher decides |
| 4 | A2: `toprope-proxy`, after ADR-0052 | |

Every importer's output is `proposed`: a person confirms it (ADR-0041). None runs the self
domains' loop.

## Done when
Every row is done; each importer has a worked example in `examples/`, and A1's demo turns this
repository's own `AGENTS.md` into candidates and conflicts.
