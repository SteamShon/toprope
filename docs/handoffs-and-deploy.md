# Handoffs and the local deploy adapter

Link: ③ ⑥. M0a item 14 (ADR-0022, ADR-0024). This is what the M1 Delivery domain
models: Authoring hands an approved version to Delivery, and Delivery previews and deploys
it locally.

## Handoffs
Declare them as in [`domain-schema.md`](domain-schema.md#handoffs). At runtime:

```python
from toprope.exec import Execution
from toprope.handoff import LocalTransport
delivery = Execution(delivery_domain, delivery_store, identity)
authoring = Execution(authoring_domain, authoring_store, identity,
                      transport=LocalTransport({"delivery": delivery}))
authoring.submit(token, "approve_version", "V1", idempotency_key="k1")   # hands off after the append
authoring.dispatch()                                                      # retry anything still pending
```

- **Contract at compile time.** `toprope-harness --domain authoring.domain.yaml --receiver
  delivery.domain.yaml@1` runs it before the harness and fails on any issue. In code: `toprope.decl.check_handoffs(sender, {"delivery":
  (delivery_domain, 1)})` checks each handoff against the receiver's published interface:
  - the domain, the action, and the interface major
  - `system` in the receiver's actor rule
  - required and unknown params, and literal or direct-path types
- **Sending.** The sender's action appends a `HandoffRequested` event (kind `outbox`)
  atomically, and the dispatcher sends it after the append. A failure never blocks or rolls
  back the sender's action.
- **The receiver's command.** It runs as `system` (`handoff:<sender>.<name>`, ADR-0026) on behalf of the
  origin person. Its idempotency key and `causation` are the handoff id
  `<name>:<sender stream>@<version>`.
- **Resolution.** The outcome is recorded in the sender's stream `handoff:<id>` as
  `HandoffDelivered`, `HandoffDenied` or `HandoffFailed`. Transient outcomes and
  unreachable receivers stay pending, and `dispatch()` retries them.

## Composition (ADR-0026)
A `*.composition.yaml` declares the members (declaration and published interface major) and
the wiring. Its format is in [`domain-schema.md`](domain-schema.md#handoffs).

```bash
uv run toprope-harness --composition self.composition.yaml     # members, wiring and contracts, then each member's harness
uv run toprope-worldmap --composition self.composition.yaml --out world-map.json
```

In code:
- `toprope.compose.assemble(composition, stores, identity)` returns one Execution per
  member, wired in process. Each receiver accepts only its wired handoffs.
- `how_to_reach_across(map, ...)` answers path questions across domains. A handoff step is
  taken by `system`.

## Local deploy
Delivery's actions, taken with `toprope-run` ([`workflow.md`](workflow.md)), call the kernel's
`preview` and `deploy` services; `toprope-commits deployed` reads the environment:

```bash
$R --member delivery preview example:2-cd34…:local
$R --member delivery deploy example:2-cd34…:local          # only a person
uv run toprope-commits deployed --env .toprope/env        # what runs, its history, and server_args
uv run toprope-server <server_args> --identity static:tokens.yaml
```

An environment moves only to a **commit** (ADR-0029); there is no build-only path. `deploy`
enforces the **fixed floor** (ADR-0022, ADR-0029), which no declaration can weaken:
- the commit is approved and is what `main` points to (not superseded), and is not the deployed
  commit or one of its ancestors (not a downgrade; rollback comes in M2). ADR-0033. The move
  happens under a per-environment lock
- the commit holds no element with `status: proposed` (ADR-0041): approval already refuses
  them, and this catches a commit approved before it did
- the build is untainted: the same declaration, and the same toolchain that ran the harness
- the harness passed
- a person approves
- no object in the environment would be stranded (migration plans come in M0b)

Refusals are logged in `deployments.jsonl` next to the deploys.

## Limits (ADR-0024)
- Delivery is in-process only: `toprope-server` does not send handoffs yet (M0b).
- `--approver` is self-declared in the local adapter. After the M1 switch-over, approval is a
  Delivery action resolved through Identity.
- The floor's taint check covers the declaration and toolchain hashes. Taint from a
  background full run comes with the result cache (sub-PR 9).
