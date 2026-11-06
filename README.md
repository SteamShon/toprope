# Toprope

**Your agent knows how to call Stripe. It doesn't know your refund policy.**

- It knows Meta Ads. It doesn't know that new creatives go to a test campaign first.
- It knows GitHub. It doesn't know who may approve a release.
- It knows your admin console's API. It doesn't know which steps come in which order.

Toprope turns what your team decided into tools and rules your agent follows. It checks every
action, by an agent or a person, against those rules, and it reviews changes to the rules the
way code changes are reviewed.

> Status: **a research prototype.** *Built* below means it runs today; *planned* names the
> milestone ([Terms](#terms)). What is done and what is left: [`docs/STATUS.md`](docs/STATUS.md).

---

## Who it is for

**Teams connecting agents to the tools they work in.** The agent can call the API, but your
policies live in a wiki, a prompt or someone's head, so nothing stops it from skipping one.
With Toprope the policies are a declaration the agent acts through: what it may not do is refused
with the reason, and what only a person may do, it cannot do.

**Teams building an agent product.** Every support ticket means another prompt fix, and every fix
breaks something that used to work. With Toprope each case you fix becomes a scenario in the
declaration, and a change to the rules shows which scenarios it breaks before it ships.

**Teams running operations with agents: marketing, support, finance.** You work out a policy by
looking at the numbers, and a week later someone, or some agent, does it the old way. With
Toprope the policy you found stays written down where it is enforced, and changing it goes
through review, with a record of why.

## Try it

An agent proposes ad budget changes; a person approves them
([`examples/paid-media/`](examples/paid-media/), runs locally with no keys):

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

| Who | Asks | Result |
|---|---|---|
| the agent | raise the holdout campaign to 1200 | denied: *Holdout campaigns keep their budget; changing it would break the test.* |
| the agent | raise `C-search` from 1000 to 2500 | denied: *Raise a daily budget by at most 500 at a time.* |
| the agent | raise `C-search` to 1400 | proposed |
| the agent | approve it | denied: *Only a person can approve_budget_change.* |
| the media lead | approve it | approved: the daily budget is 1400 |

From the same file you also get MCP tools for the agent, a command line, a guide, and tests that
try every state × action × role combination:

```
harness: PASS (model, execution, mcp)
cells: 12 decided, covered model 12, execution 12, mcp 12; 0 undecided; 0 without an instance
```

Raise the step limit to 1000, and before it ships you see what the change touches:

```
changes 1 precondition(s); affects 4 cell test(s), 1 precondition test(s), exploration; replays past propose_budget_change
passes; 0 error(s), 0 warning(s)
```

In this example, approving updates Toprope's own record. Calling the ad platform needs an adapter
(*planned*, M0b). A smaller example: [`examples/refunds/`](examples/refunds/).

## Why Toprope

- **Works with the agent you already use.** Agents reach it over MCP: Claude Code, Codex, Cursor
  or your own.
- **Rules your agent cannot skip.** Every action passes one check that refuses what is not allowed,
  gives the reason, and records the attempt.
- **Rules reviewed like code.** A change is a commit, checked before review, approved by a person
  merging it into `main`, and deployed only if its tests pass. Why we think every workflow needs
  this loop: [`docs/problem.md`](docs/problem.md).
- **Tests you do not write.** The harness is generated from the declaration and tries every
  state × action × role combination.
- **You do not write the rules either.** An agent drafts them from your systems and your answers to
  plain questions, such as *"Can someone approve an experiment that is already running?"*, and a
  person confirms each one.
- **Small and local.** A Python library and a server you run yourself, with no hosted service.

## How to adopt it

1. Run an example (above).
2. Declare one workflow: let your agent interview you about it, and confirm what it drafts.
3. Serve it over MCP to the agent that does the work.
4. Put one write action behind it: the one that would hurt most if the agent got it wrong.
5. Connect it to the system that action changes (adapters: *planned*, M0b).

## What it gives you

| | Status |
|---|---|
| a declaration: objects and links, actions, a transition matrix (next state or a refusal, per state and action) and invariants (rules that always hold) | built |
| functions that compute over the domain | planned (M0b) |
| the gate every action passes through, and an event log of actions, refusals and decisions | built |
| MCP tools, a command line, a guide, a generated harness | built |
| a UI, a backend for systems that do not exist yet, query tools over the history | planned (M0b) |
| commits, the change check, approval by merge, deploys of approved commits only ([`docs/commits.md`](docs/commits.md)) | built |
| adapters to existing systems, with read-back | planned (M0b) |
| proposals for the next change, from the history | planned (M4) |

Toprope's own workflows, making a domain and delivering it, are declared the same way, and their
tools are generated from those declarations; only a small kernel is hand-built. More:
[`docs/how-it-works.md`](docs/how-it-works.md).

## Use cases, supported by Toprope

Domains declared with Toprope and used for real, each with its declaration and what it governs.
None yet: the first is milestone M2. To add yours, open a PR with the declaration and a short
description of the workflow.

## Limits

- It covers only actions that go through it.
- A declaration cannot yet see whose agent acted, so a person could approve a change their own
  agent proposed ([`docs/STATUS.md`](docs/STATUS.md), *Left from reviews*).
- It says whether an action was *allowed*, not whether the rules are right or a decision was good.
- None of the claims below is tested yet.

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
