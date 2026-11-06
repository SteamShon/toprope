# Toprope

**Our view: coding agents do well partly because code gives them a loop. A PR to propose in,
tests and static analysis to check before merge, a review, a deploy, and logs to learn from.
Team workflows have no such loop. Toprope is an attempt to give them one.**

Toprope lets a team write down its workflow rules (who may do what, in which state, and what
must always hold) as a versioned declaration. Every action by an agent or a person is checked
against it, and changes to the rules are checked and approved the way code changes are. It is
for teams that let agents act on systems with state: refunds, experiments, campaigns, releases.

> Status: **a research prototype.** Toprope runs on its own two workflows (making a domain and
> delivering it), which shows once that the approach can be built, not that it works better; no
> claim is measured yet. Below, *built* means it runs today; *planned* names the milestone
> ([Terms](#terms)). What is done and what is left: [`docs/STATUS.md`](docs/STATUS.md).

---

## An example: a refund window

A support lead decides that promo orders are refundable for 7 days. Today that rule lives in a
wiki, a support script and an agent's prompt. With Toprope it is one declaration
([`examples/refunds/`](examples/refunds/); runnable, and checked by a test):

```yaml
actions:
  refund_order:
    actor: [support]
    target: Order
    preconditions:
      - id: within-window
        check: target.days_since_purchase <= 7
        reason: Refunds are allowed within 7 days of purchase.
transitions:
  Order:
    field: status
    matrix:
      paid:     {refund_order: refunded}
      refunded: {refund_order: {deny: "This order is already refunded."}}
```

An agent, or anyone, asks to refund an order bought 8 days ago. Toprope refuses it, with the
reason that was declared, and records the refused attempt:

```
$ toprope-run … refund_order O-8
{"status": "denied", "code": "within-window", "reason": "Refunds are allowed within 7 days of purchase.", …}
```

Later someone proposes 30 days. Before it ships, the change is compared with the current rules:

```
changes 1 precondition(s); affects 4 cell test(s), 1 precondition test(s), exploration; replays past refund_order
passes; 0 error(s), 0 warning(s)
```

In the commit workflow, a person then approves the change by merging it into `main`, and only
then is it deployed. Nobody edits three copies: the agent's tools, the command line and the
guide all come from the same declaration. Two limits of this example: the order's age is a
stored number because timers are *planned* (M0b), and putting the check in front of a real
payment system needs an adapter, also *planned* (M0b).

## Why coding agents work, and why the rest of the work does not

There are many explanations for why coding is where agents work best: abundant training data,
outputs that can be checked, work that is already text, developers who adopt early. Ours is one
more, and the one this project is built on. Code already runs through a loop a machine can
drive, and in our experience the work between people does not:

| | Code | A team workflow, in our experience | With Toprope |
|---|---|---|---|
| What is true now | `main` | in people's heads | the declaration on `main` |
| A change | a PR, a diff against `main` | applying it is the change | a commit, with a diff of what changed in domain terms |
| Checked before merge | tests, types, static analysis, CI | rarely, and from memory | the change check and generated tests, recorded on the commit |
| Review | a reviewer approves | an approval, if someone asks for one | only a person approves, by merging into `main` |
| Deploy | only reviewed commits | there is nothing to deploy | only approved commits whose tests passed |
| Afterwards | logs feed the next PR | lost in chat | every action, refusal and decision in an event log |

So an agent asked to refund an order or change a campaign has the APIs but not what the team
**decided**. Cases from the researcher's experience (observed, not measured; details changed):

| What was decided | What happened |
|---|---|
| "This promotion is refundable for 7 days only." | Support made one exception, it became the custom, and nobody knew which was right. |
| "This campaign is a holdout: don't touch its budget." | Another team raised the budget. The money was already spent. |
| "A device, once assigned, never changes group." | It had been broken for three weeks when someone noticed, after a decision was made on those numbers. |

The rules existed, but only as speech, so nothing could check them. Why prose in `AGENTS.md` or
a wiki falls short too, and why stronger models make this matter more:
[`docs/problem.md`](docs/problem.md).

## Where this comes from

The researcher (the project's author) uses coding agents heavily, and over time that work turned
into what people have started calling *loop engineering* and *graph engineering*:

- **Loop engineering**: designing the cycle the agent works in, so each attempt is checked and
  corrected before it counts. The agent writes a change, the tests reject it, it fixes it, and
  only a passing change goes to review.
- **Graph engineering**: fixing which steps may follow which, so the agent cannot skip one. No
  deploy before review; no review before the tests pass.

What made those loops trustworthy was not the agent's script but a boundary it could not cross
unchecked: tests, types, a protected `main`. Code has the parts for that boundary. Work that is
not code usually has no tests to fail, no base to diff against and no CI, so the people doing it
can neither build such a loop nor guarantee one.

For that work, we think the boundary is the set of moves the domain allows, so that is what
Toprope asks people to declare. They do not write it: an agent drafts it from their systems and
from their answers to plain questions (*"Can someone approve an experiment that is already
running?"*), and they confirm each part. The loop around changing it is not theirs to build
either. It is the same for every user, because it is itself a declared domain (see
[Toprope runs on itself](#toprope-runs-on-itself)). This is one answer we are testing, not *the*
answer.

## What Toprope does

1. **Declare the domain** (*built*; functions *planned*, M0b). In the style of DDD
   (domain-driven design): an ontology of the work (objects and links), the actions that change
   it and the functions that compute over it. Over them sit the rules: a **transition matrix**
   (for each state and action, the next state or a refusal with its reason) and **invariants**
   (what must always hold). The matrix is the graph of allowed moves, so it can be drawn (the
   world map) and tested cell by cell.
2. **Change it the way code changes** (*built*). Nobody declares a domain right the first time,
   so the declaration needs its own loop. A change is a commit with a diff of what changed in
   domain terms. The change check runs on it: an impact report like the one above, broken
   references, conflicting rules, regressions, and what past actions would have done under the
   new rules. A person approves by merging into `main`; only approved commits whose tests passed
   are deployed ([`docs/commits.md`](docs/commits.md)). Review comments that become interview
   questions are *planned*.
3. **Generate what people and agents use** (*built in part*). MCP tools (MCP is the protocol
   agents such as Claude Code use to call tools), a command line, a guide, and a **harness**:
   generated tests that try each cell of the matrix and check every invariant after each step.
   A UI, a backend for systems that do not exist yet, and query tools over the history are
   *planned* (M0b). We bet (hypothesis ③, tested in M2) that code passing a harness over the
   whole matrix can be trusted, so writing it becomes nearly free.
4. **Refuse and record** (*built*). Every action goes through one check, the Execution gate,
   which refuses anything the declaration does not allow and gives the declared reason.
   Actions, refusals and decisions land in an event log. Proposing the next change from that
   history is *planned* (M4).

## What it guarantees, and what it does not

The person designing the workflow does not have to build the guarantees; the parts every
domain shares (the kernel) hold them:

- Only a person approves a change, and only a change whose checks passed.
- Nothing deploys without a passing harness.
- The harness tries every cell its example data can reach, and reports the cells it cannot.
- Every action, allowed or refused, is recorded.

What it does not do:

- It does not keep the author of a change from approving it. Separate authors and approvers
  wait until a domain has more than one owner (M2 or later).
- It cannot say whether the declared rules are *right*, or whether a decision was *good*. That
  stays with people. Whether the interview gets the rules right is what links ① and ② test.
- It covers only actions that go through it.

## Brownfield is the case we design for

Most work runs on systems that already exist, and the check has to sit in front of the systems
people already use. So we design for **brownfield**: Toprope holds what was decided about your
servers, APIs and databases and refuses what that does not allow before the call reaches them.
**Greenfield**, where nothing exists yet, is the case where Toprope generates the backend too.
Neither is built: today the Execution gate runs in front of Toprope's own event log and a local
deploy, and the first brownfield adapter is planned for M0b. The layers:
[`docs/how-it-works.md`](docs/how-it-works.md).

## Toprope runs on itself

Making a domain and delivering it are workflows too. Toprope's own **Authoring** (draft,
interview, commit, check, approve) and **Delivery** (preview, deploy, verify) are declared
domains, the *self domains*. Their declarations drive the loop above through a small set of
built-in services, and their tools and guides are generated. Only the kernel is hand-built. So
the process is not fixed: who reviews, how many approve and what must pass before a deploy are
lines in a declaration that can be changed. The kernel keeps the rules no declaration can weaken.

**It is not** an agent framework (use the agent you have), a guardrail product (enforcement
follows from the model; it is not the goal), or a hosted service. It fits where there is state,
allowed actions and rules, and poorly where there is little to declare.

## Claim status

The project is a chain of claims, each tested by a milestone with a verdict rule written down
before the run: ① a domain can be changed safely, ② the model ends up right, ③ software
generated from it works in real use, ④ people and agents act on the same meaning, ⑤ it improves
through use, ⑥ handoffs between people get faster. Details and what would weaken each:
[`docs/charter.md`](docs/charter.md#3-the-claim-chain).

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
| domain, declaration | one area of work (refunds, experiments) and the YAML file that declares it |
| transition matrix | for each state and action: the next state, or a refusal with its reason |
| invariant | a rule that must hold after every action |
| Execution gate | the one check every action passes through |
| harness | tests generated from the declaration; its *small world* is the example data it runs on |
| change check | the checks a change gets before it is approved, starting with the impact report |
| kernel | the hand-built core every domain shares; everything else is generated |
| self domains | Authoring and Delivery: Toprope's own workflows, declared as domains |
| MCP | Model Context Protocol, how agents call tools |
| ADR | an architecture decision record, in [`docs/adr/`](docs/adr/) |
| P0, ①–⑥ | the premise (nobody declares a domain right the first time) and the claims above |
| M0a … M5 | milestones: M0a the core (done), M1 Toprope on itself (now), M0b UI and adapters to existing systems, M2 a real domain with an outside expert ("dogfood"), M3–M5 the later claims ([`docs/roadmap.md`](docs/roadmap.md)) |

## Read next

| To | Read |
|---|---|
| feel the problem | [`docs/problem.md`](docs/problem.md) |
| see how it works | [`docs/how-it-works.md`](docs/how-it-works.md), [`docs/domain-model.md`](docs/domain-model.md), [`docs/commits.md`](docs/commits.md) |
| understand the design and its claims | [`docs/charter.md`](docs/charter.md), [`docs/architecture.md`](docs/architecture.md) |
| use it | [`examples/refunds/`](examples/refunds/), [`docs/workflow.md`](docs/workflow.md), [`docs/kernel-commands.md`](docs/kernel-commands.md), [`docs/server.md`](docs/server.md) |
| write a declaration | [`docs/domain-schema.md`](docs/domain-schema.md), [`docs/semantics.md`](docs/semantics.md) |
| follow the project | [`docs/STATUS.md`](docs/STATUS.md), [`docs/roadmap.md`](docs/roadmap.md), [`docs/adr/`](docs/adr/) |
| contribute | [`AGENTS.md`](AGENTS.md): branch from `develop`, PR into `develop`, name the link your change serves |

Working notes in Korean: [`notes/ko/`](notes/ko/).

## License

No license yet, so all rights are reserved. The repository is private until M1 reports, and
Apache-2.0 is the proposed license (ADR-0005).
