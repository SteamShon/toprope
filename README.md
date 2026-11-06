# Toprope

**Our view: coding agents do well partly because code gives them a loop. A PR to propose in,
tests and static analysis to check before merge, a review, a deploy, and logs to learn from.
Team workflows have no such loop. Toprope is an attempt to give them one: git's model for the
domain, with a software factory on top.**

A correctness layer between agents and the systems they drive, aimed at stateful domains where
people and agents act.

> Status: **M1 in progress**, and no claim is measured yet. Toprope runs on its own two domains,
> which shows once that the approach can be built, not that it works better. Below, *built*
> means it runs today for those domains; *planned* names the milestone. What is done and what
> is left: [`docs/STATUS.md`](docs/STATUS.md). Verdicts: [Claim status](#claim-status).

---

## Why coding agents work, and why the rest of the work does not

There are many explanations for why coding is where agents work best: abundant training data,
outputs that can be checked, work that is already text, developers who adopt early. Ours is one
more, and the one this project is built on. Code already runs through a loop a machine can
drive: what is true now is on `main`, a change is a diff against it, tests and static analysis
check it before a person looks, nothing lands without approval, a pipeline deploys only what
was approved, and logs show what happened. An agent can propose, be checked, be corrected and
learn inside that loop. In our experience, the work between people lacks it:

| | Code | A team workflow, in our experience | With Toprope (built for its own domains) |
|---|---|---|---|
| What is true now | `main` | in people's heads | the declared domain on `main` |
| A change | a PR, a diff against `main` | applying it is the change | a commit on a branch, with a semantic diff |
| Checked before merge | tests, types, static analysis, CI | rarely, and from memory | the change check, and a generated harness, recorded on the commit |
| Review | a reviewer approves | an approval, if someone asks for one | only a person approves, by merging into `main` |
| Deploy | only reviewed commits | there is nothing to deploy | only approved commits, and only if the harness passed |
| Afterwards | logs feed the next PR | lost in chat | every action, denial and decision in an event log |

So an agent asked to refund an order, launch an experiment or change a campaign has the APIs
but not what the team **decided**: who may approve, what must be true first, what is not
allowed today. Cases from the researcher's experience (observed, not measured; details changed):

| What was decided | What happened |
|---|---|
| "This promotion is refundable for 7 days only." | Support made one exception, it became the custom, and nobody knew which was right. |
| "This campaign is a holdout: don't touch its budget." | Another team raised the budget. The money was already spent. |
| "A device, once assigned, never changes group." | It had been broken for three weeks when someone noticed, after a decision was made on those numbers. |

The rules existed, but only as speech, so nothing could check them. Why we expect prose in
`AGENTS.md` or a wiki to fall short too, and why we think stronger models make this matter
more: [`docs/problem.md`](docs/problem.md).

## Where this comes from

The researcher uses coding agents heavily, and over time that work turned into what people
have started calling *loop engineering* and *graph engineering*:

- **Loop engineering**: designing the cycle the agent works in, so that each attempt is checked
  and corrected before it counts. For example: the agent writes a change, the tests and the type
  checker reject it, it fixes it, and only a passing change goes to review.
- **Graph engineering**: fixing which steps may follow which, so that the agent cannot skip one.
  For example: no deploy before review, no review before the tests pass.

What made those loops trustworthy was not the agent's script. It was a boundary the agent could
not cross unchecked: tests, types, a protected `main`. Developers can build that boundary because
code already has the parts. Work that is not code usually has no tests to fail, no base to diff
against and no CI to run, so the people doing it have neither the experience nor a way to
guarantee such a loop.

For non-code work, we think that boundary is the domain's set of allowed moves, so that is what
Toprope asks people to declare. They do not write it. They answer plain questions, an agent
drafts an **ontology** (objects and links), the **actions** that change it and the **functions**
that compute over it from their answers and their systems, and they confirm. We expect few
people to write such a model by hand (a hypothesis). The loop around changing it is not theirs
to build either: it is Toprope's own declared Authoring and Delivery domains, the same for every
user. This is one answer we are testing, not *the* answer.

| What a loop or a graph needs | Where it is in Toprope | Status |
|---|---|---|
| a graph of the allowed moves | the transition matrix, roles and preconditions; the world map draws it | built |
| a check that the graph is kept | the Execution gate, and a generated harness over the matrix | built (model, Execution and MCP levels) |
| a loop on the declaration | commit → change check → approve → deploy | built |
| a loop from use | event log → proposals → a person decides | log built; proposals planned (M4) |
| a graph between domains | composition and typed handoffs (ADR-0026) | built in part |
| functions | typed function ports (ADR-0015) | planned (M0b) |

The person designing the workflow does not have to know how to guarantee any of this; the
kernel and the compiler hold it. Only a person approves, only a commit whose checks passed, and
nothing deploys without a passing harness. The harness tries every cell its small world can
reach and reports the ones it cannot. Separate authors and approvers wait until a domain has
more than one owner (M2 or later). Two limits remain: whether the interview really gets a model
right is what links ① and ② test, and the matrix can say whether an action was *allowed*, not
whether the decision was *good*. That stays with people.

## Brownfield is the case we design for

Most work runs on systems that already exist, and the boundary has to sit in front of the
systems people already use, so we design for **brownfield** first: Toprope is meant to hold what
was decided about your servers, APIs and databases and refuse what that does not allow before the
call reaches them. **Greenfield** is the case where there is nothing yet and Toprope generates
the backend too. Neither is built: today the Execution gate runs in front of Toprope's own event
log and a local deploy, and the first brownfield adapter is planned for M0b. The layers:
[`docs/how-it-works.md`](docs/how-it-works.md).

## What Toprope does

1. **Declare the domain, DDD-style** (*built*; functions *planned*, M0b). An ontology, its
   actions and functions, and the rules over them: a **transition matrix** (who may do what, in
   which state) and **invariants** (what must always hold). The matrix is the graph of allowed
   moves. Because it is declared, it can be drawn (the world map) and tested cell by cell.
2. **Change it the way code changes** (*built*). Nobody declares a domain right the first time
   (the premise, P0), so the declaration needs its own loop. Every change is a commit on a branch
   with a semantic diff. The change check runs on it: an impact report in domain terms
   (*"changes 2 cells; affects 14 tests, 1 invariant"*), broken references, conflicting rules,
   regressions, and what past events would have done under the new rules. A person approves by
   merging into `main`, and Delivery deploys only approved commits whose harness passed
   ([`docs/commits.md`](docs/commits.md)). GitHub-style review, where comments become
   interview questions, is *planned*.
3. **A software factory** (*built in part*). From the declaration Toprope generates MCP tools, a
   command line (`toprope-run`), a guide, and a **harness**: generated tests that try each cell
   of the matrix and check every invariant after each step. A generated UI, a greenfield backend
   and query tools are *planned* (M0b). The bet, link ③ and a hypothesis until M2, is that code
   which passes a harness over the whole matrix can be trusted, so writing it becomes nearly free.
4. **Refuse and record** (*built*). Every action goes through the Execution gate, which checks
   the declaration and refuses with the declared reason. Actions, denials and decisions land in
   an event log. Proposing the next change from that history is *planned* (M4).

One declaration reads as two sentences:

| For the domain | For an agent |
|---|---|
| Only an approver may approve an experiment. | An engineer's `approve_experiment` is refused, with the reason. |
| Nothing runs without an approver. | The gate refuses any step that would leave a running experiment without `approved_by`, and the harness's bounded exploration looks for a sequence that does. |

The declaration behind it: [`docs/how-it-works.md`](docs/how-it-works.md#a-taste-of-the-declaration).

## Toprope runs on itself

Making a domain and delivering it are workflows too. Toprope's own **Authoring** (draft,
interview, commit, check, approve) and **Delivery** (preview, deploy, verify) are declared
domains. Their declarations orchestrate the loop above over a small set of kernel services, and
their tools and guides are generated. Only the kernel is hand-built. So the process is not fixed:
who reviews, how many approve, and what must pass before a deploy are lines in a declaration that
can be changed. The kernel keeps the rules no declaration can weaken.

**It is not** an agent framework (use the agent you have), a guardrail product (enforcement
follows from the model; it is not the goal), or a hosted service. It fits where there is state,
allowed actions and rules, and poorly where there is little to declare.

## Claim status

Each link of the claim chain is tested by a milestone with a preregistered verdict. The chain,
the hypotheses and what would weaken each: [`docs/charter.md`](docs/charter.md#3-the-claim-chain).

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
