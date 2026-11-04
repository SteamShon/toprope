# Lineage

Toprope continues work the researcher did at a previous employer (Liner) and restarts it as
personal research. The researcher states that code and IP are not a concern. Even so, the
design here starts from written problem statements and public sources, and claims nothing
from prior work as measured evidence.

## The original motivation

Individual productivity rose with agents; organizational productivity did not. Looking at
why, the researcher found that the workflows *between* people — getting code into the
product, designing an experiment and moving a metric — were implicit and oral, so agents
could not automate them and decisions did not accumulate. Toprope's answer was to model
workflows as domains (an ontology plus actions) so people and agents share one language,
generate MCP and UI from that model, and improve it from logs through agent proposals and
human decisions.

## Prior threads

| Prior framing | Relation here |
|---|---|
| Toprope: World Model (Object/Link/Action/Policy/Contract/Flow), Domain Capsule, generated MCP and explainer UI, Gate, self-compile | **Core.** Restarted with a minimal core (ADR-0010) |
| "A decision is state" essay: decisions as declared state, N×M → N+M, block / exception / amendment | Accumulation and lifecycle (M3). Enforcement is a property, not the goal (ADR-0007) |
| Domain Authoring / Domain Delivery | The factory loop (M2, M3) |
| Domains: PID, Growth, PMO, Media, Product Delivery | Experiment lifecycle (M1) draws on PID/Growth. Product Delivery is the second domain (M4) |
| Expert harness reuse: survive the 2nd and 3rd change without the author | Measured in M2 (H-Factory) |
| Unified knowledge lifecycle (2026-10-23) | Proposal → decision loop (M3) |
| Like: data → state → action → outcome → response models | Thread C, deferred. The decision log is its future dataset |

## Evidence levels carried over

- *Observed once, not measured*: PMO/Media had working definitions and connections; three
  domains were built with the approach; a 48-question owner interview (~1h) surfaced a
  mis-recorded agreement; top-tier coding agents lost direction on long tasks without
  planning and intervention.
- *Explicitly unmeasured*: whether the approach made anyone or any team faster.

## Public references

- [S1] Temporal: Workflow Definition. https://docs.temporal.io/workflow-definition
- [S2] LangGraph overview. https://docs.langchain.com/oss/python/langgraph/overview
- [S3] CopilotKit OpenDots README. https://github.com/CopilotKit/OpenDots
- [S4] Harness²: Recursive Agent Harnessing for an Open World. arXiv:2610.14224v1
- Palantir Foundry Ontology: object types, link types, action types, functions (the
  conceptual reference for "workflow ≡ domain").
- Model Context Protocol specification (the agent surface).
- Codd, E. F. (1970). A Relational Model of Data for Large Shared Data Banks.
