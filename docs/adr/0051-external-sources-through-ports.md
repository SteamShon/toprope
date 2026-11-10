# ADR-0051: External sources come in through ports, and their lifecycle is a domain

- Link: ② model is right (a declaration starts from what a team already wrote down), ⑤ evolves
  (a changed source becomes a proposal), ⑥ · Status: decisions 1–3 **accepted**, 2026-11-10,
  decided by SteamShon ("제안한 방향대로 … port adapter로 외부에서 끼워넣기 쉽게"; drafted by the
  assistant); decisions 4–5 **proposed**, for the researcher, built after M1's recheck
- Builds on: ADR-0011 (adapters at the edge), ADR-0041 (one way across), ADR-0049 (A1)

## Context
ADR-0049's A1 asked for importers from OpenAPI, database enums and ticket workflows. Written one
per format, each team's conventions (which field is a stage, where roles live, what to skip) are
code, and every new source or convention is a code change. Yet the steps are the same for every
source: reach it, read its format, turn what it says into candidate elements that cite their
place, list what it cannot say, and let a person confirm. And sources change after the import:
an API grows an operation, a workflow a status. Nothing notices that the declaration no longer
matches.

Generators of this material already exist, and rebuilding them is no part of Toprope. NVIDIA Auto
Ontology (Apache-2.0, reviewed 2026-11-10) builds terms, facts and joins from database metadata
with a model, and people certify them; it exchanges them as Apache Ossie, whose converters cover
dbt, Snowflake, Databricks, Salesforce and others. These tools describe what things *are*; none
says what may *happen* to them (actions, stages, who may act), which is what a declaration adds.
So their output should come in through an extractor for their exchange format, as one more source.

## Decision
1. **Two ports.** A **Reader** reaches a source where it lives (a file, a URL, an API) and returns
   its bytes and the ref that citations start from. An **Extractor** reads one format and returns
   **candidates**: an element path as `propose_element` takes it, its value, and its exact place;
   with the questions the source cannot answer and the conflicts it contains (both places named).
   `toprope-import <extractor> <source> --via <reader>` composes them.
2. **Plugged in from outside.** A package registers readers and extractors through the entry-point
   groups `toprope.readers` and `toprope.extractors` (or `register_reader` / `register_extractor`
   in code). The built-ins (readers `file`, `http`; extractors `openapi`, `sql`, `workflow`)
   register the same way. A plugin that fails to load is reported and skipped.
3. **Conventions are data.** A **profile** (YAML) carries what varies between teams: the fields
   that are stages, the roles to use, where an operation names its roles (e.g. `x-roles`), names to
   ignore or rename, the thing a workflow moves, and `options` for a plugged-in extractor. A wrong
   key is refused with the keys it may have.
4. *(proposed)* **The lifecycle of a source is a domain.** Registered → read → extracted →
   reviewed, and, when the source changes, **drift**: the extractor runs again, its candidates are
   compared with the declaration, and each difference becomes a proposal citing the new place. It
   is declared and run like Authoring and Delivery (a self domain, *Sources*, handing proposals to
   Authoring), so who may register a source, approve a reviewed import or silence a drift is a
   rule, with its record.
5. *(proposed)* **Readers and extractors are kernel services of that domain**, called as declared
   effects (ADR-0028); their results stay proposals (ADR-0041).

## Consequences
- What an importer writes is always `proposed`; ports never decide anything enforced.
- A new source needs one extractor (code: it parses a format), and no change to Toprope; a new
  convention needs a profile.
- A generator such as Auto Ontology is used, not rebuilt: it runs as its own service, and Toprope
  reads its export (Ossie) through an extractor. It is never a dependency of Toprope.
- Decisions 4 and 5 change the self domains' composition, so they wait for M1's recheck (AGENTS.md,
  one loop at a time).

## Open, for the researcher (decisions 4–5)
1. A third self domain (*Sources*, handing to Authoring), or a stage inside Authoring?
   (Recommended: its own domain: a source has a lifecycle and permissions of its own, and drift
   continues after a declaration is done.)
2. Drift: on a schedule, on a webhook, or on demand? (Recommended: on demand and on a schedule
   first; webhooks with the M0b adapters.)
