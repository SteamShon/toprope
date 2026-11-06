# Toprope

**Coding agents work because code gives them a loop: a PR to propose in, tests and static
analysis to check before merge, a review, a deploy, and logs to learn from. Team workflows have
no such loop. Toprope gives a workflow one: git and GitHub for the domain, and a software
factory on top.**

A correctness layer between agents and the systems they drive, for any stateful domain where
people and agents act.

> Status: **M1 in progress**, and no claim is measured yet. What is done and what is left:
> [`docs/STATUS.md`](docs/STATUS.md). Verdicts: [Claim status](#claim-status).

---

## Why coding agents work, and why the rest of the work does not

Of everything agents do, coding works best, and not only because models are good at code.
Code is the one place where the work already runs through a loop that a machine can drive: what is true now is on `main`, a change is a diff against it, tests and static
analysis check it before a person looks, nothing lands without approval, a pipeline deploys
only what was approved, and logs show what happened. An agent can propose, be checked, be
corrected and learn, all inside that loop.

The work between people has none of it.

| | Code | A team workflow today | With Toprope |
|---|---|---|---|
| What is true now | `main` | in people's heads | the declared domain on `main` |
| A change | a PR, a diff against `main` | applying it is the change | a commit on a branch, with a semantic diff |
| Checked before merge | tests, types, static analysis, CI | not at all | the change check and a harness over every state × action × role, recorded on the commit |
| Review | a reviewer approves | the approver's memory, if anyone asks | a person approves: a merge into `main` |
| Deploy | only reviewed commits | there is nothing to deploy | only approved commits, and only if the harness passes |
| Afterwards | logs feed the next PR | lost in chat | every action, denial and decision in an event log, feeding the next change |

So an agent asked to refund an order, launch an experiment or change a campaign has the APIs
but not what the team **decided**: who may approve, what must be true first, what is not
allowed today.

| What was decided | What happened |
|---|---|
| "This promotion is refundable for 7 days only." | Support made one exception, it became the custom, and nobody knows which is right now. |
| "This campaign is a holdout: don't touch its budget." | Another team raised the budget. The money was already spent. |
| "A device, once assigned, never changes group." | It had been broken for three weeks when someone noticed, after a decision was made on those numbers. |

The rules existed. They were only spoken, so nothing could check them. Writing them into
`AGENTS.md` or a wiki does not help: nothing tells you whether a new line conflicts with the
old ones, and every copy drifts. And stronger models make it worse: a model can work out what
is *right*, not what *you decided*, and the longer it runs alone, the further a wrong premise
goes. The long version: [`docs/problem.md`](docs/problem.md).

## Agents drive existing systems; Toprope sits in between

```
 Intelligence   agents (Claude Code, Codex, any MCP client) and people
       │        propose actions through surfaces generated from the domain
       ▼
 Toprope        the declared domain, the gate that checks every action, the event log
       │        only allowed actions pass
       ▼
 Effects        brownfield: the servers, APIs and databases you already have, behind adapters
                greenfield: a backend Toprope generates, when there is none
```

Most work runs on systems that already exist, so **brownfield is the first-class case**:
Toprope does not replace your systems. It holds what was decided about them and refuses what
the decision does not allow, before the call reaches them. Greenfield is the case where there
is nothing yet, and Toprope generates the backend too. (The first brownfield adapter is
planned for M0b; see [`docs/roadmap.md`](docs/roadmap.md).)

## What Toprope does

1. **Declare the domain, DDD-style.** Objects, actions, a **transition matrix** (who may do
   what, in which state) and **invariants** (what must always hold). An agent drafts it from
   your code, docs and an interview; the owner only answers plain questions, such as *"Can
   someone approve an experiment that is already running?"*, and confirms.
2. **Change it like code: git and GitHub for the domain.** Every change is a commit on a branch
   with a semantic diff. The change check runs on it: an impact report in domain terms
   (*"changes 2 cells; affects 14 tests, 1 invariant"*), conflicting rules, regressions, and what
   past events would have done under the new rules. Review comments become interview questions.
   A person approves by merging into `main`, and Delivery deploys only approved commits
   ([`docs/commits.md`](docs/commits.md)).
3. **A software factory.** From the declaration it generates what people and agents use: MCP
   tools, a command line, a guide, a backend for greenfield, and a harness that tests **every**
   cell of the matrix and every invariant, not a sample of call paths. When the harness passes,
   the code is trusted because the model is, so writing it is nearly free.
4. **Refuse and record.** Every action goes through one gate that checks the declaration and
   refuses with the declared reason. Actions, denials and decisions land in an event log, which
   is where the next change is proposed from.

One declaration reads as two sentences:

| For the domain | For an agent |
|---|---|
| Refunds are allowed within 7 days. | A refund after day 7 cannot run. |
| Only an approver may approve an experiment. | An engineer's `approve_experiment` is refused, with the reason. |
| Nothing runs without an approver. | No sequence of actions reaches `running` without `approved_by`. |

```yaml
transitions:                  # state × action → next state | deny(reason) | n/a | undecided
  Experiment:
    field: status
    matrix:
      draft:    {approve_experiment: approved, launch_experiment: {deny: "Launch requires approval."}}
      approved: {approve_experiment: {deny: "Already approved."}, launch_experiment: running}
invariants:
  - id: running-has-approver
    on: Experiment
    check: target.status not in ['running', 'ended', 'decided'] or exists(target.approved_by)
    reason: Nothing runs without someone having approved it.
```

## Toprope runs on itself

Making a domain and delivering it are workflows too. Toprope's own **Authoring** (draft,
interview, commit, check, approve) and **Delivery** (preview, deploy, verify) are declared
domains, and the git-and-GitHub loop above is generated from those declarations. Only the
kernel is hand-built. This is also why your process is not fixed: who reviews, how many
approve, what must pass before a deploy are lines in a declaration you can change. The kernel
keeps the rules no declaration can weaken.

**It is not** an agent framework (use the agent you have), a guardrail product (enforcement
follows from the model; it is not the goal), or a hosted service. It fits where there is state,
allowed actions and rules, and poorly where there is little to declare. How the pieces fit:
[`docs/how-it-works.md`](docs/how-it-works.md).

## What is proven so far

Toprope is built as a chain of claims, each tested by a milestone with a preregistered verdict
([`docs/charter.md`](docs/charter.md)). Running on itself shows the approach can be built. It
does not yet show that it is better than a natural-language skill or that it makes a team
faster. That is what the milestones measure.

## Claim status

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

## Read next

| To | Read |
|---|---|
| feel the problem | [`docs/problem.md`](docs/problem.md) |
| see how it works | [`docs/how-it-works.md`](docs/how-it-works.md), [`docs/domain-model.md`](docs/domain-model.md), [`docs/commits.md`](docs/commits.md) |
| understand the design and its claims | [`docs/charter.md`](docs/charter.md) (problem, claim chain, hypotheses, principles), [`docs/architecture.md`](docs/architecture.md) |
| use it | [`docs/workflow.md`](docs/workflow.md) (who runs what, when), [`docs/kernel-commands.md`](docs/kernel-commands.md), [`docs/server.md`](docs/server.md) |
| write a declaration | [`docs/domain-schema.md`](docs/domain-schema.md), [`docs/semantics.md`](docs/semantics.md) |
| follow the project | [`docs/STATUS.md`](docs/STATUS.md), [`docs/roadmap.md`](docs/roadmap.md), [`docs/experiments/M1-self-compile.md`](docs/experiments/M1-self-compile.md), [`docs/adr/`](docs/adr/) |
| contribute | [`AGENTS.md`](AGENTS.md): branch from `develop`, PR into `develop`, name the link your change serves |

Working notes in Korean: [`notes/ko/`](notes/ko/).

## License

Not chosen yet. The repository stays private until M1 has a verdict. Apache-2.0 is the
proposal (ADR-0005).
