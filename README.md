# Toprope

Toprope is a light, open foundation. It turns the hidden workflows between people into a
**domain model that people and agents both use**, and it keeps that model improving while
it is used.

Agents raised individual productivity. Organizational productivity did not follow, because
the work *between* people runs on implicit, oral process: getting code into the product,
or designing an experiment and moving a metric. Agents cannot automate what is not written
down, and the decisions made along the way do not accumulate, so nobody can learn from them.

## The claim chain

Everything in this repository is organized around one premise and five claims. Each claim
only matters if the one before it holds.

```
P0 premise          nobody can define a domain correctly in one go; it is found by iterating
      ↓
① iterate safely    a domain can be changed cheaply and safely: breakage and conflicts are
                    caught at compile time and the change can be tried before deployment
      ↓
② model is right    through those iterations, the model comes to capture how the work runs
      ↓
③ shared language   MCP and UI generated from the model let people and agents act on the same meaning
      ↓
④ evolves           use accumulates decisions, and the model improves
      ↓
⑤ org productivity  handoff delay and re-explanation between people go down
```

## Claim status

| Link | Hypothesis | Verdict in | Status |
|---|---|---|---|
| ① iterate safely | H-Iterate | M1 (self), M2 (dogfood) | untested |
| ② model is right | H-Fidelity | M1 (self), M2 (dogfood) | untested |
| ③ shared language | H-Shared | M3 | untested |
| ④ evolves | H-Evolve | M4 | untested |
| ⑤ org productivity | H-Handoff (partial) | M5 | untested |

Status values: `untested` · `supported` · `weakened` · `refuted`. This table is updated
only when an experiment reaches its preregistered verdict.

## Documents

- [`docs/charter.md`](docs/charter.md): problem, what Toprope is, the chain, hypotheses, principles
- [`docs/roadmap.md`](docs/roadmap.md): milestones, each defined by the link it gives a verdict on
- [`docs/experiments/M1-self-compile.md`](docs/experiments/M1-self-compile.md): first experiment, which models Toprope itself
- [`docs/architecture.md`](docs/architecture.md): bounded contexts, ports and adapters
- [`docs/domain-schema.md`](docs/domain-schema.md): minimal domain core
- [`docs/adr/`](docs/adr/): project decisions with provenance
- [`notes/ko/`](notes/ko/): working notes in Korean
- [`AGENTS.md`](AGENTS.md): branching, PR and merge conventions for people and coding agents

## Ground rules

- Every document, experiment and ADR names the link(s) it serves.
- Small, falsifiable milestones. Evenings and weekends (~10h+/week).
- Reuse OSS for everything that is not a link in the chain.
- Claims state their evidence level: *measured*, *observed once*, or *hypothesis*.
