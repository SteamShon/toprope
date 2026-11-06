# Toprope

**Declare what your team decided, who may do what and in which state, and every action by an
agent or a person is checked against it. Changes to those rules are checked and approved the
way code changes are.**

For teams that let agents act on systems with state: ad budgets, refunds, incidents, releases,
experiments.

> Status: **a research prototype.** *Built* below means it runs today; *planned* names the
> milestone ([Terms](#terms)). No claim is measured yet. What is done and what is left:
> [`docs/STATUS.md`](docs/STATUS.md).

---

## The situation

**An agent that changes ad budgets.** LangChain's open-source
[Paid Media Agent](https://github.com/langchain-ai/paid-media-agent) analyses campaigns across ad
platforms and drafts budget changes for a person to approve. To make those writes safe, its
authors built by hand a typed proposal, an approval bound to that exact proposal, one attempt
and a readback, a reviewed list of allowed operations, a kill switch, and tests that edited
payloads, replays and foreign users are refused. That is careful work, and it is code written
for one domain. The team's own rules, such as "never touch a holdout campaign", would be one
more layer on top.

**An agent in an incident.** A summary of a Netflix talk reports that an average incident
involves nine teams and more than 30 engineers over hours, and describes an operational ontology
(services, devices, users and how they connect) built so that agents can triage and suggest fixes
([summary](https://www.sysdesai.com/news/ZASM29wJUJdp),
[talk](https://www.infoq.com/presentations/netflix-observability-aiops-ontology-scale/)). An
ontology tells an agent what is connected. It does not say which fixes the agent may apply, in
which incident state, and with whose approval.

In both cases the hard part is not calling an API. It is the rules around the call, which today
live in code written for one agent, in prompts, or in people's heads.

## The same rules, declared

Here is the ad-budget case as a Toprope declaration ([`examples/paid-media/`](examples/paid-media/),
runnable and checked by a test):

```yaml
actions:
  propose_budget_change:
    actor: [analyst]                 # the agent
    preconditions:
      - id: not-a-holdout
        check: target.holdout == false
        reason: Holdout campaigns keep their budget; changing it would break the test.
      - id: step-limit
        check: params.daily_budget - target.daily_budget <= 500
        reason: Raise a daily budget by at most 500 at a time.
  approve_budget_change:
    actor: [media_lead]
    requires: human
    preconditions:
      - id: not-the-proposer
        check: target.proposed_by != actor.id
        reason: Whoever proposed a change cannot approve it.
```

Then the agent tries:

| Who | Asks | Result |
|---|---|---|
| the agent | raise the holdout campaign to 1200 | denied: *Holdout campaigns keep their budget; changing it would break the test.* |
| the agent | raise `C-search` from 1000 to 2500 | denied: *Raise a daily budget by at most 500 at a time.* |
| the agent | raise `C-search` to 1400 | proposed |
| the agent | approve it | denied: *Only a person can approve_budget_change.* |
| the media lead | approve it | approved: the daily budget is 1400 |

Every attempt, allowed or refused, is recorded. The same declaration also gives the agent its
MCP tools, gives people a command line and a guide, and gives a harness that tries every state ×
action × role combination:

```
harness: PASS (model, execution, mcp)
cells: 12 decided, covered model 12, execution 12, mcp 12; 0 undecided; 0 without an instance
```

When someone proposes raising the step limit to 1000, the change is compared with the current
rules before it ships, and a person approves it:

```
changes 1 precondition(s); affects 4 cell test(s), 1 precondition test(s), exploration; replays past propose_budget_change
passes; 0 error(s), 0 warning(s)
```

Not built yet: the call to the ad platform and the readback (an adapter, planned M0b). Today
approving updates Toprope's own record. A smaller example: [`examples/refunds/`](examples/refunds/).

## The idea

Code changes run through a loop: a diff against `main`, tests before review, a person approves,
only approved commits deploy, and logs show what happened. Most other work has no such loop.
Toprope gives a workflow the same one:

| | Code | A team workflow today | With Toprope |
|---|---|---|---|
| What is true now | `main` | in people's heads | the declaration on `main` |
| A change | a diff against `main` | applying it is the change | a commit, with a diff in domain terms |
| Checked before merge | tests, types, CI | rarely | the change check and the generated harness |
| Review | a reviewer approves | an approval, if someone asks | only a person approves, by merging into `main` |
| Deploy | only reviewed commits | nothing to deploy | only approved commits whose harness passed |
| Afterwards | logs | lost in chat | every action, refusal and decision in an event log |

Why we think this is missing, and why stronger models make it matter more:
[`docs/problem.md`](docs/problem.md).

## What one declaration gives you

1. **The domain** (*built*): objects and links, the actions that change them, a **transition
   matrix** (for each state and action: the next state, or a refusal with its reason) and
   **invariants** (rules that must always hold). An agent drafts it from your systems and your
   answers to plain questions; a person confirms each part. *Functions* that compute over the
   domain are *planned* (M0b).
2. **A gate** (*built*): every action passes one check that refuses anything not allowed and
   records what happened.
3. **Generated surfaces** (*built in part*): MCP tools for agents, a command line, a guide, and
   the harness. A UI, a backend for systems that do not exist yet, and query tools over the
   history are *planned* (M0b).
4. **A review loop for the rules** (*built*): commits, the change check, approval by merging into
   `main`, and deploys of approved commits only ([`docs/commits.md`](docs/commits.md)).

Toprope's own workflows, making a domain and delivering it, are declared the same way, and their
tools are generated from those declarations; only a small kernel is hand-built. More:
[`docs/how-it-works.md`](docs/how-it-works.md).

## Limits

- It covers only actions that go through it. Sitting in front of your existing systems needs
  adapters (planned, M0b).
- A declaration cannot yet see whose agent acted, so a person could approve a change their own
  agent proposed ([`docs/STATUS.md`](docs/STATUS.md), *Left from reviews*).
- It can say whether an action was *allowed*, not whether the rules are right or a decision was
  good.
- Whether this works better than rules in prompts or skills, and whether people can get their
  rules into it through an interview, is untested. That is what the milestones measure.

## Claim status

Each claim is tested by a milestone with a verdict rule written down before the run: ① a domain
can be changed safely, ② the model ends up right, ③ software generated from it works in real
use, ④ people and agents act on the same meaning, ⑤ it improves through use, ⑥ handoffs
between people get faster ([`docs/charter.md`](docs/charter.md#3-the-claim-chain)).

| Link | Hypothesis | Verdict in | Status |
|---|---|---|---|
| ① iterate safely | H-Iterate | M1 (self), M2 (dogfood) | untested |
| ② model is right | H-Fidelity | M2 (an application domain whose expert is not Toprope's builder; ADR-0030) | untested |
| ③ works as built | H-Factory | M2 (dogfood use) | untested |
| ④ shared language | H-Shared | M3 | untested |
| ⑤ evolves | H-Evolve | M4 | untested |
| ⑥ org productivity | H-Handoff (partial) | M1 (self handoff, partial), M5 | untested |

Status values: `untested` · `supported` · `weakened` · `refuted`. The `Status` column
changes only in a PR that reports a preregistered experiment verdict.

## Terms

| Term | Meaning |
|---|---|
| domain, declaration | one area of work (ad budgets, refunds) and the YAML file that declares it |
| transition matrix | for each state and action: the next state, or a refusal with its reason |
| invariant | a rule that must hold after every action |
| gate (Execution gate) | the one check every action passes through |
| harness | tests generated from the declaration, run on the model, the gate and the MCP server |
| change check | the checks a change to the rules gets before it is approved, starting with an impact report |
| kernel | the hand-built core every domain shares; everything else is generated |
| MCP | Model Context Protocol, how agents such as Claude Code call tools |
| ADR | an architecture decision record, in [`docs/adr/`](docs/adr/) |
| ①–⑥ | the claims above |
| M0a … M5 | milestones: M0a the core (done), M1 Toprope on its own workflows (now), M0b UI and adapters to existing systems, M2 a real domain with an outside expert ("dogfood"), M3–M5 the later claims ([`docs/roadmap.md`](docs/roadmap.md)) |

## Read next

| To | Read |
|---|---|
| try it | [`examples/paid-media/`](examples/paid-media/), [`examples/refunds/`](examples/refunds/) |
| see how it works | [`docs/how-it-works.md`](docs/how-it-works.md), [`docs/domain-model.md`](docs/domain-model.md), [`docs/commits.md`](docs/commits.md) |
| the problem, at length | [`docs/problem.md`](docs/problem.md) |
| the design and its claims | [`docs/charter.md`](docs/charter.md), [`docs/architecture.md`](docs/architecture.md) |
| use it | [`docs/workflow.md`](docs/workflow.md), [`docs/kernel-commands.md`](docs/kernel-commands.md), [`docs/server.md`](docs/server.md) |
| write a declaration | [`docs/domain-schema.md`](docs/domain-schema.md), [`docs/semantics.md`](docs/semantics.md) |
| follow the project | [`docs/STATUS.md`](docs/STATUS.md), [`docs/roadmap.md`](docs/roadmap.md), [`docs/adr/`](docs/adr/) |
| contribute | [`AGENTS.md`](AGENTS.md): branch from `develop`, PR into `develop`, name the link your change serves |

Working notes in Korean: [`notes/ko/`](notes/ko/).

## License

No license yet, so all rights are reserved. The repository is private until M1 reports, and
Apache-2.0 is the proposed license (ADR-0005).
