# ADR-0024: The handoff outbox, string joining, and the local deploy floor

- Link: ③ works as built, ⑥ org productivity (H-Handoff) · Status: **proposed** (assistant
  draft; the researcher accepts or amends) · 2026-11-04
- Amends: `docs/semantics.md` step 12 (details only), the check language (ADR-0010)

## Context
Roadmap M0a item 14 implements handoffs (ADR-0022) and a local deploy adapter. The schema
and semantics define what a handoff is. Implementing it needed four details they leave open,
and one change to the check language that the schema's own example already assumes
(`target.domain_id + ':' + target.number`).

## Decision
1. **The outbox is the event log.** The interpreter emits a `HandoffRequested` event (kind
   `outbox`) with the evaluated target and params, the receiving domain and action, and the
   origin person. It is appended **atomically with the sender's events** in step 11, so a
   handoff exists if and only if its action happened. Projection ignores it. The model and
   every runtime level emit it identically, so parity covers it.
2. **Identity and idempotency.** The handoff id is
   `<handoff>:<sender stream>@<outbox event version>`. It is the receiver's idempotency key
   and the `causation` field of the receiver's events (a new field on commands and events).
   This links the two stores and makes retries deliver at most once.
3. **Resolution.** After the append, a dispatcher sends pending requests through a
   `HandoffTransport` port (M0a: in-process; across processes: M0b). It records exactly one
   resolution per handoff in the sender's store, in its own stream `handoff:<id>`:
   - `HandoffDelivered` when the receiver returns ok
   - `HandoffDenied` when the receiver's rules deny it (`docs/semantics.md`)
   - `HandoffFailed` when the mapping could not be evaluated or the receiver rejected the
     command (not-found, exists, invalid params)
   - nothing for a transient outcome (`conflict`, `in-progress`) or an unreachable receiver:
     it stays pending and the next dispatch retries it.

   Resolutions use their own stream so they never bump the sender object's version and never
   cause conflicts with the sender's own commands. The receiver acts as `system`
   (`handoff:<name>`) on behalf of the origin person (an agent's principal). That actor can
   only come from a transport, never from credentials (Identity refuses it).
4. **String joining in the check language.** `+` joins a string with a string or an
   integer. Floats, booleans, null and lists are refused (fail closed), so no value has two
   renderings. Arithmetic is unchanged.
5. **The local deploy floor.** `toprope-deploy` previews a build (the harness, the world
   map, and the build's declaration hash plus toolchain hash). It deploys only if four rules
   hold, enforced in code and never in a declaration:
   - the build is untainted: the same declaration, and the same toolchain that ran the
     harness
   - the harness passed
   - a person approves
   - no object in the environment would be stranded

   Until migration plans exist (M0b), a stranding deploy is refused.

## Consequences
- Handoffs move from "M1" to "implemented (M0a)" in the schema status table.
- The cross-domain contract is checked at compile time (`check_handoffs`). It covers an
  unknown domain or action, the interface major, `system` in the receiver's actor rule,
  missing or unknown params, and literal or direct-path type mismatches.
- Not yet: a cross-process transport, external-effect adapters (`Effect*` events), and
  delivery from a background worker (M0a dispatches right after each append and on demand).
