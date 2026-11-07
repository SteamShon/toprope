# Example: a refund window

Link: none (an example for the README). A one-object domain: support may refund a paid order
within 7 days of purchase. `tests/test_examples.py` checks that it gives the output below.

Timers are not built yet (M0b), so the order's age is a stored number, `days_since_purchase`,
rather than computed from a purchase date.

## Run it

```bash
uv sync
R="uv run toprope-run --domain examples/refunds/refunds.domain.yaml --seed \
   --identity static:examples/refunds/tokens.yaml --token t-sam"
$R refund_order O-8     # day 8: refused
$R refund_order O-3     # day 3: refunded
```

Day 8:
```json
{"status": "denied", "code": "within-window", "reason": "Refunds are allowed within 7 days of purchase.", ...}
```

## Change the window to 30 days

`refunds.30-days.domain.yaml` is the same declaration with `<= 30`. The change check compares
the two before anything is deployed:

```bash
uv run python -c '
from toprope.decl import load_domain; from toprope.check import change_check
r = change_check(load_domain("examples/refunds/refunds.30-days.domain.yaml"),
                 load_domain("examples/refunds/refunds.domain.yaml"))
print(r.impact["summary"]); print(r.summary())'
```

```
changes 1 precondition(s); affects 4 cell test(s), 1 precondition test(s), exploration; replays past refund_order
passes; 0 error(s), 0 warning(s)
```

With a deployed event store (`events=`), the check also replays past refunds under the new
rule. In the self domains the same check runs on a commit, and a person approves the commit
by merging it into `main` ([`docs/commits.md`](../../docs/commits.md)).
