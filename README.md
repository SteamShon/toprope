# Toprope

> A decision is state, not a note.

Toprope is a personal, non-commercial research project on one question:

**When a person makes a decision about how an agent should work, can that decision be
captured from ordinary work, approved once, and then actually hold on the execution
path — without the person re-explaining it every session?**

Today those decisions live in prompts, `CLAUDE.md`/`AGENTS.md`, wikis, and people's heads.
Agents are *asked* to read them. Nothing stops a call that contradicts them, nothing
notices when the copy in one place goes stale, and nothing turns repeated corrections
into an explicit, revisable rule.

Toprope studies the loop:

```
work history ──► decision candidates ──► human approval ──► declared decision (state)
     ▲                                                              │
     │                                                              ▼
 corrections / exceptions ◄── read-back & audit ◄── gate on the execution path
```

## Status

Pre-M0. Documents and plan only. No claims of results yet — see
[`docs/roadmap.md`](docs/roadmap.md) for what will be measured and what would falsify it.

## Read in this order

1. [`docs/research-charter.md`](docs/research-charter.md) — problem, scope, questions, hypotheses, non-goals
2. [`docs/roadmap.md`](docs/roadmap.md) — milestones with exit and kill criteria
3. [`docs/experiments/M1-enforce.md`](docs/experiments/M1-enforce.md) — the first experiment
4. [`docs/architecture.md`](docs/architecture.md) — domain model and ports/adapters
5. [`docs/decision-schema.md`](docs/decision-schema.md) — draft declaration format
6. [`docs/adr/`](docs/adr/) — decisions made about this project, with provenance
7. [`docs/lineage.md`](docs/lineage.md) — where these ideas come from and what is *not* carried over

Working notes in Korean live under [`notes/ko/`](notes/ko/).

## Ground rules

- Small, falsifiable milestones. Evening/weekend time budget (~10h+/week).
- Reuse OSS for everything that is not the research question.
- Every claim states its evidence level: *measured*, *observed once*, or *hypothesis*.
- Domain meaning never lives inside a host UI or a specific runtime (DDD, ports/adapters).
