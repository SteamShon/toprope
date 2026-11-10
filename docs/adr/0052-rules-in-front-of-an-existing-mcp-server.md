# ADR-0052: Rules in front of an existing MCP server

- Link: ③ works as built (the rules hold on the tools agents already call), ⑥ · Status:
  **accepted**, 2026-11-10, decided by SteamShon ("추천대로": the recommendation on each open
  point; drafted by the assistant; ADR-0049, A2)
- Builds on: ADR-0011 (adapters at the edge), ADR-0016 (actors and principals), ADR-0024 (the
  outbox), ADR-0028 (kernel services as declared effects), ADR-0041 (one way across), ADR-0050
  (approvals by risk), ADR-0051 (external sources through ports)

## Context
A team's agents already call MCP servers: a ticket tracker, a payments API, a deploy tool. The
rules about those calls (who may refund, in which state a ticket may close, what needs a second
person) live in prompts and `AGENTS.md`, so an agent that does not read them, or reads them
wrong, breaks them. Toprope enforces a declaration on its own server (`toprope-server`), but a
team will not move its tools behind a new server to get that. ADR-0049's A2 asks for the other
way round: put the rules in front of the server the team already has.

Toprope already has the parts. An action can call a service as a declared effect and take the
result in a reply action, at most once, keyed by the effect id (ADR-0028, ADR-0024). A late reply
after someone moved the object changes nothing (#148). Approvals by risk say which actions wait
for a person (ADR-0050). The import ports can read a server's tool list (ADR-0051).

## Decision
1. **`toprope-proxy` is an MCP server that stands where the upstream server stood.** An agent
   connects to the proxy; the proxy is a client of the upstream server. The agent sees the tools
   it is bound to (decision 2), with the same names and input schemas, so its prompts and code do
   not change.
2. **A binding says which action a tool is.** A YAML file next to the declaration maps each
   upstream tool to a declared action. It names the argument that identifies the target object
   (or that the tool creates one), maps the tool's arguments to the action's params, and names
   the reply action that records the result. A tool with no binding is **not offered**
   (fail-closed). A tool the binding marks `read: true` (and the server annotates `readOnlyHint`)
   passes through unchanged, recorded but not gated.
3. **The gate decides before the call; the reply records the result.** A bound call runs the
   action through the kernel like any other command: actor, preconditions, the transition cell,
   outcome rules (ADR-0048). If it is refused, the agent gets the refusal with its reason and
   fix, and the upstream server is never called. If it is allowed, the action's `call` effect
   (ADR-0028) is the upstream tool call. Its result comes back as the reply action: success moves
   the object on, failure is recorded and moves nothing. Execution is at most once by the effect
   id, so a retry does not call upstream twice.
4. **Toprope's log is the gate's state.** The proxy decides from the object's state in
   Toprope's event log, not by asking upstream. The log starts from an import (ADR-0051) or from
   a read the binding names. If upstream changes something behind the proxy's back, the two
   disagree. Noticing that is the Sources domain's drift (ADR-0051, decision 4), not the proxy's.
5. **Who calls is mapped, not trusted.** The proxy maps the MCP client's identity to an actor
   and, for an agent, its principal (ADR-0016), through the binding's identity map until M0b's
   adapters bring identity mappings. An unmapped caller is refused.
6. **An action that needs a person waits, and the agent is told so.** When ADR-0050's tiers say
   an action needs approval, the proxy does not call upstream. It answers with a refusal that
   names the pending approval and who may give it. Once a person approves, the same call (same
   arguments, same effect id) goes through. MCP has no callback, so the agent asks again.
7. **The binding is drafted by import, and confirmed by a person.** A reader `mcp` lists a
   server's tools (`tools/list`); an extractor turns them into proposed actions with typed params
   from each input schema, and a draft binding. Nothing is gated until a person confirms the
   actions and the binding (ADR-0041).

## Consequences
- An agent keeps its tools; the declaration's rules hold on every call it makes through the
  proxy. A call that bypasses the proxy (a direct connection to upstream) is not governed. Taking
  away direct access is the team's deployment choice, which the docs must say plainly.
- The upstream server's own errors stay its own: the proxy records them and moves nothing.
- One more process in the path. Its latency is the kernel's check plus the upstream call.
- A minimal proxy fits this umbrella: stdio and streamable HTTP upstreams, a static identity map,
  the binding file, the gate through `Execution`. Identity providers, timers and a hosted proxy
  come with M0b's adapters.

## Decided on the open points (2026-11-10)
1. **Unbound tools are hidden** (fail-closed). The import drafts a binding for every tool, so
   leaving one out is a choice a person makes.
2. **Read-only tools pass through**, recorded but not gated. Gating reads waits for read
   visibility (`read`, M0b).
3. **An action that waits for approval is refused**, naming the approval; the agent asks again
   once a person decides. MCP has no callback, and a held call would time out.
4. **The gate's state is Toprope's log.** Drift from upstream is found by the Sources domain
   (ADR-0051, decision 4), not by a read before every call.
5. **The minimal proxy is built in this umbrella** (theme 4's last item). It needs no M0b part.
