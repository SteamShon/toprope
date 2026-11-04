# Architecture (draft)

First requirement: **domain meaning is independent of any host, runtime or model.**
DDD bounded contexts with ports and adapters. Swapping an adapter must keep the same
decisions with the same limits — that is the test of replaceability, not interface shape.

## Bounded contexts

| Context | Owns | First milestone |
|---|---|---|
| **Decision** | declared decisions, versions, scope, owner, status (proposed/active/withdrawn/superseded) | M0 |
| **Enforcement** | evaluating an intended action against active decisions → verdict (allow / deny / ask / exception) | M0 |
| **Audit** | append-only events: proposed, approved, evaluated, blocked, excepted, amended, read-back | M0 |
| **Authoring** | candidates mined from history, evidence quotes, review outcomes | M2 |
| **Lifecycle** | triage of contradictions, exception accumulation, amendment proposals | M3 |
| **Effect** | read-back of real effects; `UNKNOWN` outcomes | M3 |

## Ports

| Port | Responsibility | First adapter | Later candidates |
|---|---|---|---|
| `DecisionStore` | load/save versioned decisions | YAML files in repo | SQLite, git-backed |
| `PolicyEvaluator` | intended action + decisions → verdict | built-in matcher | Cedar, OPA/Rego |
| `ActionSource` | translate a host's pre-action event into a canonical `IntendedAction`, and a verdict back | Claude Code `PreToolUse` hook | Codex hooks, MCP proxy, LangGraph node |
| `AuditLog` | append events | JSONL file | SQLite, OpenTelemetry |
| `HistorySource` | read agent transcripts | Claude Code session JSONL | Codex logs, chat exports |
| `CandidateExtractor` | history → candidates with evidence | LLM call (Claude API) | rule-based, Harness²-style probes |
| `Reviewer` | human accept/edit/reject | CLI | web UI, host panel |
| `EffectReader` | re-read real state after an action | filesystem / git | provider APIs |

## Canonical flow (M0–M1)

```
host (Claude Code) ──PreToolUse JSON──► ActionSource adapter
                                           │  IntendedAction{tool, args, cwd, session}
                                           ▼
                         Enforcement ◄── DecisionStore (active decisions)
                                           │  Verdict{allow|deny, decision_id, reason}
                          AuditLog ◄───────┤
                                           ▼
host ◄── deny + reason (exit 2 / permissionDecision) or allow
```

## Guarantee boundary (stated up front)

- The gate sees only actions that pass through its `ActionSource`. Any other path
  (another tool, a script the agent writes and runs, a different host) is outside the
  guarantee. M1 measures bypass attempts; M3 documents the boundary.
- The gate guarantees a decision is *applied*, not that it is *right*.
- Matching shell commands by pattern is approximate; false allows/blocks are measured.

## Deferred choices

Runtime (Temporal, LangGraph) and host (OpenDots) are not needed while the execution path
is an agent hook. They enter only when a milestone requires durable multi-step workflows
or a shared UI, and only behind the ports above.
