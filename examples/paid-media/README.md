# Example: an agent proposes ad budget changes

Link: none (an example for the README). An agent analyses campaigns and proposes budget
changes; a person approves them. The rules are the team's: holdout campaigns are never
touched unless a media lead grants a one-time exception, a budget rises by at most 500 a day at
a time, and whoever proposed a change cannot approve it. `tests/test_examples.py` checks that it
gives the output below.

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
| the agent (`bot`) | raise the holdout campaign to 1200 | denied: *Holdout campaigns keep their budget; changing it would break the test. A media lead can grant a one-time exception.* |
| the agent | raise `C-search` from 1000 to 2500 | denied: *Raise a daily budget by at most 500 at a time.* |
| the agent | raise `C-search` to 1400 | proposed |
| the agent | approve it | denied: *Only a person can approve_budget_change.* |
| `ana` (media lead) | approve it | approved: the daily budget is 1400 |

A person who proposes a change and then tries to approve it gets *Whoever proposed a change, or
had their agent propose it, cannot approve it.*

`bot` acts on behalf of `eli`. `proposed_by` records `actor.principal.id`, the person an agent
answers for, so a proposal by `bot` is `eli`'s, and `eli` cannot approve it either (ADR-0041).

## An exception

Exceptions are not a construct of their own (ADR-0041, Resolved 6). They are a pattern: an action
a person takes that records a decision and sets a flag, and a rule that reads the flag.

```yaml
  grant_exception:
    actor: [media_lead]
    requires: human
    effects:
      - set: {target.exception_approved: true}
    records_decision: true
# the holdout rule:      target.holdout == false or target.exception_approved == true
# approving a change:    sets target.exception_approved back to false, so it is used once
```

```bash
$R --token t-ana grant_exception C-holdout --rationale "the test ended early"
$R --token t-bot propose_budget_change C-holdout --daily-budget 1200 --reason "best CPA"
$R --token t-ana approve_budget_change C-holdout
```

| Who | Asks | Result |
|---|---|---|
| the agent | grant an exception | denied: *Only a person can grant_exception.* |
| `ana` | grant an exception, with a rationale | granted; recorded as a decision with the rationale |
| the agent | raise the holdout campaign to 1200 | proposed |
| `ana` | approve it | approved: the daily budget is 1200, and the exception is used up |
| the agent | raise it again | denied, as before the exception |

Every exception is a recorded decision with its reason, so how many pile up on a rule is visible
in the history, the input ADR-0041 names for proposing that the rule change (M4).

## Test it

```bash
uv run toprope-harness --domain examples/paid-media/paid-media.domain.yaml
```
```
harness: PASS (model, execution, mcp)
cells: 16 decided, covered model 16, execution 16, mcp 16; 0 undecided; 0 without an instance
invariants exercised: 1/1
```

## Change a rule

`paid-media.step-1000.domain.yaml` raises the step limit to 1000. The change check compares it
with the current rules before anything ships:

```
changes 1 precondition(s); affects 4 cell test(s), 2 precondition test(s), exploration; replays past propose_budget_change
passes; 0 error(s), 0 warning(s)
```
