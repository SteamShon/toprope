# Toprope

**Your agent knows how to call Stripe. It doesn't know your refund policy.**

- It knows Meta Ads. It doesn't know that new creatives go to a test campaign first.
- It knows GitHub. It doesn't know who may approve a release.
- It knows your admin console's API. It doesn't know which steps come in which order.

Toprope turns what your team decided into tools and rules your agent follows. It checks every
action, by an agent or a person, against those rules, and it reviews changes to the rules the
way code changes are reviewed. And when the system does not exist yet, the same declaration
builds it.

- **Govern what you have.** Put the rules in front of the tools and systems your agents already
  use.
- **Build what you need.** Declare the domain in the style of domain-driven design, and the
  software for it is generated and tested, instead of written by a coding agent line by line.

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

**Teams building a new system with coding agents.** The agent writes code fast, but nothing
says whether the code does what the domain requires, and every change risks a state nobody
meant to allow. With Toprope you declare the domain (objects, links, actions, functions, which
action is allowed in which state, and what must always hold) and generate from it the tools, the
tests that try every combination, and, as the factory grows, the backend and the UI.

**Teams running operations with agents: marketing, support, finance.** You work out a policy by
looking at the numbers, and a week later someone, or some agent, does it the old way. With
Toprope the policy you found stays written down where it is enforced, and changing it goes
through review, with a record of why.

## Try it

You need [`uv`](https://docs.astral.sh/uv/) and a clone of this repository:

```bash
git clone https://github.com/SteamShon/toprope.git && cd toprope && uv sync
```

Start a domain from a template, add a rule of your own by command, and see the gate enforce it.
No YAML is written by hand ([`docs/tutorial.md`](docs/tutorial.md) goes on to a connected agent):

```bash
export TOPROPE="$(pwd)"                              # the clone; every command runs through uv from it
uv run --project "$TOPROPE" toprope-init my-access --template approval --dir /tmp  # or budget, experiment, refunds, release
cd /tmp/my-access && uv run --project "$TOPROPE" toprope-try                        # the template's rules refuse an agent
uv run --project "$TOPROPE" toprope-add field amount --set-by submit_request --default 0
uv run --project "$TOPROPE" toprope-rule threshold --action approve_request --when "amount > 1000" --needs finance
uv run --project "$TOPROPE" toprope-try                                              # the story shows your rule refusing
uv run --project "$TOPROPE" toprope-run submit_request R-wiki --amount 1500 --token t-mia
uv run --project "$TOPROPE" toprope-run approve_request R-wiki --token t-max || echo "refused by your rule"
```
```
...
max (manager)   asks to approve request one with amount 1001
                -> denied: When amount > 1000, only finance may approve request.
kim (finance)   asks to approve request one with amount 1001
                -> done
...
refused by your rule
```

Your workflow is not a template? Start from a sentence: `toprope-init "Staff submit orders; a lead
approves them. An order over 5,000 needs a director."` picks the closest template, drafts the rules
it recognises (you confirm them with `toprope-rule confirm`) and asks about the rest. Other rule
kinds: `no-self-approval`, `person-only`, `window` (`toprope-rule --help`); `toprope-rename` fits
the template's names to yours.

A rule added this way is `proposed` unless you confirm it at the terminal where you typed it (you
are asked to type yes); a proposed rule is enforced all the same, and `toprope-rule confirm`, run by
a person at a terminal, makes it yours. This is a local guard, not authentication: there is no
identity behind it, only a check that a terminal answered. It keeps an agent that runs these
commands in a script or a pipeline from making rules a person's on its own.

### A worked example

An agent proposes ad budget changes; a person approves them
([`examples/paid-media/`](examples/paid-media/), runs locally with no keys):

```yaml
actions:
  propose_budget_change:
    actor: [analyst]                 # the agent
    preconditions:
      - id: not-a-holdout
        check: target.holdout == false or target.exception_approved == true
        reason: Holdout campaigns keep their budget; changing it would break the test. A media lead can grant a one-time exception.
      - id: step-limit
        check: params.daily_budget - target.daily_budget <= 500
        reason: Raise a daily budget by at most 500 at a time.
  approve_budget_change:
    actor: [media_lead]
    requires: human
    preconditions:
      - id: not-the-proposer
        check: target.proposed_by != actor.principal.id    # the agent's person, or the person
        reason: Whoever proposed a change, or had their agent propose it, cannot approve it.
```

| Who | Asks | Result |
|---|---|---|
| the agent | raise the holdout campaign to 1200 | denied: *Holdout campaigns keep their budget; changing it would break the test. A media lead can grant a one-time exception.* |
| the agent | raise `C-search` from 1000 to 2500 | denied: *Raise a daily budget by at most 500 at a time.* |
| the agent | raise `C-search` to 1400 | proposed |
| the agent | approve it | denied: *Only a person can approve_budget_change. Fix: ask a person to take it* |
| the media lead | approve it | approved: the daily budget is 1400 |

From the same file you also get MCP tools for the agent, a command line, a guide, and tests that
try every state × action × role combination:

```
harness: PASS (model, execution, mcp)
cells: 16 decided, covered model 16, execution 16, mcp 16; 0 undecided; 0 without an instance
```

Raise the step limit to 1000, and before it ships you see what the change touches:

```
changes 1 precondition(s); affects 4 cell test(s), 14 param test(s), 3 precondition test(s), exploration; replays past propose_budget_change
passes; 0 error(s), 0 warning(s)
```

In this example, approving updates Toprope's own record. Calling the ad platform needs an adapter
(*planned*, M0b). A smaller example: [`examples/refunds/`](examples/refunds/).

## Why Toprope

- **Works with the agent you already use.** Agents reach it over MCP: Claude Code, Codex, Cursor
  or your own.
- **Rules your agent cannot skip.** Every action passes one check that refuses what is not allowed,
  gives the reason, and records the attempt.
- **The map is the gate.** The same declaration that documents the rules is compiled into the
  check that enforces them and the tests that verify it, so what runs cannot drift from what was
  approved.
- **Rules reviewed like code.** A change is a commit, checked before review, approved by a person
  merging it into `main`, and deployed only if its tests pass. Why we think every workflow needs
  this loop: [`docs/problem.md`](docs/problem.md).
- **One approval per change.** An agent drafts a change and writes it up as one request; a person
  reads it and approves it once, in GitHub or at their own terminal (`toprope-apply`, one `yes`),
  and that approval confirms, commits, checks and approves it, and ships it when its risk is low
  ([`docs/workflow.md`](docs/workflow.md)).
- **Tests you do not write.** The harness is generated from the declaration and tries every
  state × action × role combination.
- **You do not write the rules either.** An agent drafts them from your systems and your answers to
  plain questions, such as *"Can someone approve an experiment that is already running?"*, and a
  person confirms each one.
- **Small and local.** A Python library and a server you run yourself, with no hosted service.

## How to adopt it

1. Start from a template and try it (`toprope-init`, `toprope-try`; [`docs/tutorial.md`](docs/tutorial.md)).
2. Declare one workflow: let your agent interview you about it, and confirm what it drafts.
3. Serve it over MCP to the agent that does the work.
4. Put one write action behind it: the one that would hurt most if the agent got it wrong.
5. Connect it to the system that action changes (adapters: *planned*, M0b).

## Two graphs

A Toprope domain keeps two kinds of knowledge apart.

| | **World model**: what exists and what may happen | **Context graph**: why, and what happened |
|---|---|---|
| Holds | objects, links, actions, functions, states; the rules adopted over them (transition matrix, invariants, preconditions); the permissions (roles, actor rules, `requires: human`) | observations (events, refused attempts, outcomes), interview answers, rule candidates not yet adopted, decisions with their reasons, sources, versions and open conflicts |
| Is | enforced: compiled into the gate, the tools and the tests | not enforced: it explains and proposes |
| Produces | software | reviews and the next change |

One rule joins them: a declared rule or permission changes only through a reviewed change, a
commit whose checks passed and that a person approves. Knowing a method, or having done
something before, changes nothing that is enforced. Two things sit between the graphs: the
current state, derived from the event log, is what the gate checks; and an `undecided` cell
refuses (a rule) while the question behind it stays open (context). "New creatives go
to a test campaign first" is a hypothesis in the context graph while the team checks it against
the numbers, and a rule in the world model once it is approved. Most of the context graph exists
today as separate records (event logs, sources on every element, commits, approvals, check
records); query tools over the event log are *planned* (M0b), and joining the rest into one
graph has no plan yet. More:
[`docs/how-it-works.md`](docs/how-it-works.md#two-graphs); the definition is ADR-0041.

## What it gives you

| Govern what you have | Status |
|---|---|
| the gate every action passes through, and an event log of actions, refusals and decisions | built |
| MCP tools, a command line and a guide for the agent and for people | built |
| commits, the change check, approval by merge, deploys of approved commits only ([`docs/commits.md`](docs/commits.md)) | built |
| adapters to existing systems, with read-back | planned (M0b) |
| proposals for the next change, from the history | planned (M4) |

| Build what you need | Status |
|---|---|
| a declaration: objects and links, actions, a transition matrix (next state or a refusal, per state and action) and invariants (rules that always hold) | built |
| a generated harness: every state × action × role combination, every invariant, at the model, gate and MCP levels | built |
| functions that compute over the domain | planned (M0b) |
| a generated backend and UI | planned (M0b) |
| software that passes the harness working in real use, so writing it becomes nearly free | hypothesis ③, tested in M2 |

Toprope's own workflows, making a domain and delivering it, are declared the same way, and their
tools are generated from those declarations; only a small kernel is hand-built. More:
[`docs/how-it-works.md`](docs/how-it-works.md).

## Use cases, supported by Toprope

Domains declared with Toprope and used for real, each with its declaration and what it governs.
None yet: the first is milestone M2. To add yours, open a PR with the declaration and a short
description of the workflow.

## Limits

- It covers only actions that go through it.
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
| try it | [`docs/tutorial.md`](docs/tutorial.md) (15 minutes), [`examples/paid-media/`](examples/paid-media/), [`examples/refunds/`](examples/refunds/) |
| see how it works | [`docs/concepts.md`](docs/concepts.md) (every part, and how they work together), [`docs/how-it-works.md`](docs/how-it-works.md), [`docs/domain-model.md`](docs/domain-model.md), [`docs/commits.md`](docs/commits.md) |
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
