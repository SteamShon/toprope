# ADR-0017: Deployment shapes: core library, server first, shell, optional runtime

- Link: ③ works as built, ④ shared language · Status: accepted · 2026-11-04 · decided by: SteamShon
- Supersedes: the hosting part of ADR-0007 (Aegra hosting the generated MCP) and the open
  hosting question in ADR-0011 §4
- Origin: design review 2026-11-04 (hosting question)

## Context
Toprope must be usable as an imported library and as an MCP server, without coupling to
any runtime. The intelligence layer is whatever agent the user already has (Claude Code,
Codex). Aegra, Temporal and a host app should each be optional adapters, not a required
bundle.

## Decision
```
toprope-core     Python library: declaration, compilers, Execution, harness, ports
  ├─ toprope-server   core + MCP (agents) + HTTP (greenfield API) + query tools   ← first
  ├─ embedded         a host app imports core and runs Execution in-process        ← second
  ├─ toprope-shell    generic web app: A2UI renderer + CopilotKit; hosts replace or override it
  └─ Runtime adapter  optional, only for autonomous agent workflows: Aegra / LangGraph / Temporal
```
1. **`toprope-server` is the first deployment shape.**
   - Agents connect over MCP.
   - The greenfield API and the brownfield gateway (adapters) run in the same process.
   - Minimum deployment: `toprope-server` + PostgreSQL (SQLite for tests).
2. **Embedded** is the second shape. It is the same core with no network hop, for host apps
   and for the harness itself.
3. **`toprope-shell`** is the default human surface for any domain. A host can replace it,
   or override it with its own components (ADR-0008).
4. **Aegra is off the critical path until M4.**
   - Drafting and interviewing are done by the user's own agent (e.g. Claude Code) through
     the **authoring MCP** that Toprope generates. This is also self-compile.
   - A `Runtime` adapter (Aegra first) is added when unattended workflows are needed: the
     periodic proposal engine in M4.
5. **Temporal** is a candidate adapter for the `Scheduler` port (ADR-0015) and for
   long-running brownfield effects with retries and compensation. It is not part of the
   base deployment.
6. **A2UI fallback.** A2UI is in public preview. If the M0 spike shows a blocker, the shell
   renders a minimal Toprope view spec of its own, generated from the same representation
   layer (ADR-0008 is unchanged).

## Consequences
- The M0 spike tests `toprope-server` (MCP to Claude Code) and `toprope-shell` (A2UI +
  CopilotKit + one host component). Aegra is no longer tested in M0.
- ADR-0007's pure-Python core and TypeScript frontend still stand.
