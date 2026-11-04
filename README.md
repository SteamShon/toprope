# Toprope

> Individual productivity went up. Organizational productivity did not.

Coding agents made writing code fast. But getting that code into the product, or designing
an experiment and actually moving a metric, still runs through **implicit workflows between
people**: who approves what, when a result counts, what must be true before the next step.
These rules live in oral tradition. Agents cannot automate what is not written down, and
because the decisions made at each step are not recorded as anything structured, the
organization cannot learn from them.

Toprope is a personal research project on one bet:

**Treat a workflow as a domain.** Model its entities, relationships and allowed actions —
in the spirit of an ontology plus action types — so that **people and agents perceive the
work in the same language**. Compile that model into a *domain capsule* that generates the
agent surface (MCP) and a human surface (UI) from one source. Let the person who defines the
domain use what was generated, log every run, have agents propose changes from those logs,
and let the person decide. Decisions then accumulate as versioned state instead of being lost.

```
            ┌──────────── domain model (objects · links · actions) ◄──────────┐
            │                         │                                       │
            ▼ compile                 ▼ compile                        human decides
      MCP for agents            UI for people                                 │
            │                         │                              agent proposes diff
            └──────► use the workflow ◄┘                                      │
                          │                                                   │
                          └──────────────────► event log ─────────────────────┘
```

## Status

Pre-M0. Documents and plan only. No results are claimed yet.

## Read in this order

1. [`docs/research-charter.md`](docs/research-charter.md): problem, thesis, questions, hypotheses, non-goals
2. [`docs/roadmap.md`](docs/roadmap.md): milestones with exit and kill criteria
3. [`docs/experiments/M1-shared-language.md`](docs/experiments/M1-shared-language.md): the first experiment
4. [`docs/architecture.md`](docs/architecture.md): bounded contexts, ports and adapters
5. [`docs/domain-schema.md`](docs/domain-schema.md) and [`examples/domains/`](examples/domains/): the minimal domain core
6. [`docs/adr/`](docs/adr/): decisions about this project, with provenance and supersession
7. [`docs/lineage.md`](docs/lineage.md): where the ideas come from

Working notes in Korean live in [`notes/ko/`](notes/ko/).

## Ground rules

- Small, falsifiable milestones. Evenings and weekends (~10h+/week).
- Reuse OSS for everything that is not the research question.
- Every claim states its evidence level: *measured*, *observed once*, or *hypothesis*.
- Domain meaning never lives inside a host UI, a runtime, or a model prompt (DDD, ports/adapters).
