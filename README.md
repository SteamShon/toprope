# Toprope

**Our view: coding agents do well partly because code gives them a loop. A PR to propose in,
tests and static analysis to check before merge, a review, a deploy, and logs to learn from.
Team workflows have no such loop. Toprope is an attempt to give them one: git and GitHub for
the domain, with a software factory on top.**

A correctness layer between agents and the systems they drive, aimed at stateful domains where
people and agents act.

> Status: **M1 in progress**, and no claim is measured yet. Below, *built* means it runs today
> for Toprope's own domains; *planned* means designed, with the milestone it lands in. What is
> done and what is left: [`docs/STATUS.md`](docs/STATUS.md). Verdicts: [Claim status](#claim-status).

---

## Why coding agents work, and why the rest of the work does not

There are many explanations for why coding is where agents work best: abundant training data,
outputs that can be checked, work that is already text, developers who adopt early. Ours is
one more, and the one this project is built on. Code is the kind of work that already runs
through a loop a machine can drive: what is true now is on `main`, a change is a diff against
it, tests and static analysis check it before a person looks, nothing lands without approval,
a pipeline deploys only what was approved, and logs show what happened. An agent can propose,
be checked, be corrected and learn inside that loop.

We think the work between people lacks exactly that loop:

| | Code | A team workflow today | With Toprope (built for its own domains) |
|---|---|---|---|
| What is true now | `main` | in people's heads | the declared domain on `main` |
| A change | a PR, a diff against `main` | applying it is the change | a commit on a branch, with a semantic diff |
| Checked before merge | tests, types, static analysis, CI | not at all | the change check, and a harness that tries every state × action × role cell, recorded on the commit |
| Review | a reviewer approves | the approver's memory, if anyone asks | a person approves: a merge into `main` |
| Deploy | only reviewed commits | there is nothing to deploy | only approved commits, and only if the harness passed |
| Afterwards | logs feed the next PR | lost in chat | every action, denial and decision in an event log |

So an agent asked to refund an order, launch an experiment or change a campaign has the APIs
but not what the team **decided**: who may approve, what must be true first, what is not
allowed today. Cases like these, from the researcher's experience (observed, not measured;
details changed):

| What was decided | What happened |
|---|---|
| "This promotion is refundable for 7 days only." | Support made one exception, it became the custom, and nobody knew which was right. |
| "This campaign is a holdout: don't touch its budget." | Another team raised the budget. The money was already spent. |
| "A device, once assigned, never changes group." | It had been broken for three weeks when someone noticed, after a decision was made on those numbers. |

The rules existed, but only as speech, so nothing could check them. We expect prose rules in
`AGENTS.md` or a wiki to fall short too: nothing checks a new line against the old ones, and
copies drift. The M1 pilot tests this against a natural-language skill. We also think stronger
models make the gap matter more, not less: a model can work out what is *right*, not what
*you decided*, and the longer it runs alone, the further a wrong premise goes. The long
version: [`docs/problem.md`](docs/problem.md).

## Where this comes from

The researcher uses coding agents heavily, and over time that work turned into what is now
called *loop engineering* and *graph engineering*: designing the cycle an agent proposes, gets
checked and is corrected in, and fixing which steps may follow which. Developers can do this
because code already has the parts. People whose work is not code have neither the experience
nor a way to guarantee it. So Toprope asks them for something they can answer instead: an
**ontology** of their work (objects and links), the **actions** that change it, and the
**functions** that compute over it. It then generates the loop and the graph from that. This is
one answer we are testing, not *the* answer.

| What a loop or a graph needs | Where it is in Toprope | Status |
|---|---|---|
| a graph of the allowed moves | the transition matrix, roles and preconditions; the world map draws it | built |
| a guarantee the graph is kept | the gate, and a harness that tries every cell | built (model and Execution levels) |
| a loop on the spec | commit → change check → approve → deploy | built |
| a loop from use | event log → proposals → a person decides | log built; proposals planned (M4) |
| a graph between domains | composition and typed handoffs (ADR-0026) | built in part |
| functions | typed function ports (ADR-0015) | planned (M0b) |

The person designing the workflow does not have to know how to guarantee any of this. The
guarantees sit in the kernel and the compiler: every cell is tested, nobody approves their own
change, and nothing deploys without a passing harness. Two limits are worth saying plainly.
People still cannot write an ontology by hand, so Toprope gets it through an interview, and
whether that works is what links ① and ② test. And the matrix can say whether an action was
*allowed*, not whether the decision was *good*; that stays with people.

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

Most work runs on systems that already exist, so we treat **brownfield as the first-class
case**: Toprope is meant not to replace your systems but to hold what was decided about them
and refuse what that does not allow before the call reaches them. Greenfield is the case where
there is nothing yet and Toprope generates the backend too. Both effect layers are *planned*
(M0b): today the gate runs in front of Toprope's own event log and a local deploy.

## What Toprope does

1. **Declare the domain, DDD-style** (*built*; functions *planned*, M0b). An ontology (objects
   and links), the actions that change it and the functions that compute over it. Over them sit
   the rules: a **transition matrix** (who may do what, in which state) and **invariants** (what
   must always hold). The matrix is the graph of allowed moves. Because it is declared, it can
   be drawn (the world map) and every cell of it can be tested. An agent drafts the declaration
   from your code, docs and an interview; the owner answers plain questions, such as *"Can
   someone approve an experiment that is already running?"*, and confirms.
2. **Change it like code: git and GitHub for the domain** (*built*). Nobody declares a domain
   right the first time (the premise, P0), so the spec itself needs a loop. Every change is a
   commit on a branch with a semantic diff. The change check runs on it: an impact report in domain terms
   (*"changes 2 cells; affects 14 tests, 1 invariant"*), broken references, conflicting rules,
   regressions, and what past events would have done under the new rules. A person approves by
   merging into `main`, and Delivery deploys only approved commits whose harness passed
   ([`docs/commits.md`](docs/commits.md)).
3. **A software factory** (*built in part*). From the declaration Toprope generates MCP tools,
   a command line (`toprope-run`), a guide, and a **harness**: generated tests that try every
   cell of the matrix and check every invariant after each step. A generated UI, a greenfield
   backend and query tools are *planned* (M0b). The bet, link ③ and a hypothesis until M2, is
   that code which passes a harness over the whole matrix can be trusted, so writing it becomes
   nearly free.
4. **Refuse and record** (*built*). Every action goes through one gate that checks the
   declaration and refuses with the declared reason. Actions, denials and decisions land in an
   event log. Proposing the next change from that history is *planned* (M4).

One declaration reads as two sentences (an illustration):

| For the domain | For an agent |
|---|---|
| Only an approver may approve an experiment. | An engineer's `approve_experiment` is refused, with the reason. |
| Nothing runs without an approver. | No sequence of actions reaches `running` without `approved_by`. |
| Refunds are allowed within 7 days (timers are *planned*, M0b). | A refund after day 7 cannot run. |

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
kernel is hand-built. So the process is not fixed: who reviews, how many approve, and what must
pass before a deploy are lines in a declaration that can be changed. The kernel keeps the rules
no declaration can weaken.

**It is not** an agent framework (use the agent you have), a guardrail product (enforcement
follows from the model; it is not the goal), or a hosted service. It fits where there is state,
allowed actions and rules, and poorly where there is little to declare. How the pieces fit:
[`docs/how-it-works.md`](docs/how-it-works.md).

## What is shown so far

Running on itself shows, once and on Toprope's own two domains, that the approach can be built.
It does not show that it beats a natural-language skill (M1 Phase B has not run) or that it
makes a team faster. That is what the milestones measure, one link of the claim chain at a time
([`docs/charter.md`](docs/charter.md#3-the-claim-chain)).

## Claim status

The chain, the hypotheses and what would weaken each:
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
