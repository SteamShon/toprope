# Handoffs and the local deploy adapter

Link: ③ ⑥. M0a item 14 (ADR-0022, ADR-0024 proposed). This is what the M1 Delivery domain
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
- **The receiver's command.** It runs as `system` (`handoff:<name>`) on behalf of the
  origin person. Its idempotency key and `causation` are the handoff id
  `<name>:<sender stream>@<version>`.
- **Resolution.** The outcome is recorded in the sender's stream `handoff:<id>` as
  `HandoffDelivered`, `HandoffDenied` or `HandoffFailed`. Transient outcomes and
  unreachable receivers stay pending, and `dispatch()` retries them.

## Local deploy
```bash
uv run toprope-deploy --env .toprope/envs/local preview my.domain.yaml   # build id, harness result
uv run toprope-deploy --env .toprope/envs/local deploy BUILD --approver ana
uv run toprope-deploy --env .toprope/envs/local status
uv run toprope-server $(uv run toprope-deploy --env .toprope/envs/local server-args) --identity static:tokens.yaml
```

`deploy` enforces the **fixed floor** (ADR-0022), which no declaration can weaken:
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
