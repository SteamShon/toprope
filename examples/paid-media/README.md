# Example: an agent proposes ad budget changes

Link: none (an example for the README). An agent analyses campaigns and proposes budget
changes; a person approves them. The rules are the team's: holdout campaigns are never
touched, a budget rises by at most 500 a day at a time, and whoever proposed a change cannot
approve it. `tests/test_examples.py` checks that it gives the output below.

The situation is the one LangChain's open-source
[Paid Media Agent](https://github.com/langchain-ai/paid-media-agent) handles. That project's
writes go through a typed proposal, an approval of that exact proposal, one attempt and a
readback, all written by hand in its own code (its `docs/architecture/writes-and-approvals.md`).
This example shows the decision part of that as a declaration instead.

**Not built here**: the call to the ad platform. Today approving updates Toprope's own record of
the campaign. Calling the platform and reading the result back needs a brownfield adapter
(planned, M0b).

## Run it

```bash
uv sync
R="uv run toprope-run --domain examples/paid-media/paid-media.domain.yaml \
   --store sqlite:/tmp/pm.db --identity static:examples/paid-media/tokens.yaml"
$R --seed --token t-bot propose_budget_change C-holdout --daily-budget 1200 --reason "best CPA"
$R --token t-bot propose_budget_change C-search --daily-budget 2500 --reason "best CPA"
$R --token t-bot propose_budget_change C-search --daily-budget 1400 --reason "best CPA"
$R --token t-bot approve_budget_change C-search
$R --token t-ana approve_budget_change C-search
```

| Who | Asks | Result |
|---|---|---|
| the agent (`bot`) | raise the holdout campaign to 1200 | denied: *Holdout campaigns keep their budget; changing it would break the test.* |
| the agent | raise `C-search` from 1000 to 2500 | denied: *Raise a daily budget by at most 500 at a time.* |
| the agent | raise `C-search` to 1400 | proposed |
| the agent | approve it | denied: *Only a person can approve_budget_change.* |
| `ana` (media lead) | approve it | approved: the daily budget is 1400 |

A person who proposes a change and then tries to approve it gets *Whoever proposed a change
cannot approve it.*

`bot` acts on behalf of `eli`. `proposed_by` records `actor.principal.id`, the person an agent
answers for, so a proposal by `bot` is `eli`'s, and `eli` cannot approve it either (ADR-0041).

## Test it

```bash
uv run toprope-harness --domain examples/paid-media/paid-media.domain.yaml
```
```
harness: PASS (model, execution, mcp)
cells: 12 decided, covered model 12, execution 12, mcp 12; 0 undecided; 0 without an instance
invariants exercised: 1/1
```

## Change a rule

`paid-media.step-1000.domain.yaml` raises the step limit to 1000. The change check compares it
with the current rules before anything ships:

```
changes 1 precondition(s); affects 4 cell test(s), 1 precondition test(s), exploration; replays past propose_budget_change
passes; 0 error(s), 0 warning(s)
```
