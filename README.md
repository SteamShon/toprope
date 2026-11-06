# Toprope

**Code changes go through a PR, CI and review. The rules your systems and agents act on do not.
Toprope gives those rules the same path: declared, checked before they change, and enforced
whenever anyone acts.**

A correctness layer and software factory for any stateful domain where people and agents act.

> Status: **M1 in progress**, and no claim is measured yet. What is done and what is left:
> [`docs/STATUS.md`](docs/STATUS.md). Verdicts: [Claim status](#claim-status).

---

## The problem you have probably hit

You hand an agent a task that touches a real workflow: refund an order, launch an experiment,
change a campaign. It has the APIs. What it does not have is what your team **decided**: who
may approve, what must be true first, what is not allowed today. That lived in people's heads.

- **Agents remove the half of safety that was in people's heads.** Permissions and validation
  are in the machine. *"Don't do that today, you touched it yesterday"* was a person. Replace
  the person with an agent, and that half leaves too.
- **Writing it down does not fix it.** Add a line to `AGENTS.md` or a skill, and nothing tells
  you whether it conflicts with the lines already there; you find out after deployment. Copy a
  rule into the server, the admin tool, the support script and the prompt, and the copies drift.
- **Rules have no PR.** Changing a rule is applying it. There is no base to diff against, no CI,
  and nothing left behind once it is accepted.

| What was decided | What happened |
|---|---|
| "This promotion is refundable for 7 days only." | Support made one exception, it became the custom, and nobody knows which is right now. |
| "This campaign is a holdout: don't touch its budget." | Another team raised the budget. The money was already spent. |
| "A device, once assigned, never changes group." | It had been broken for three weeks when someone noticed, after a decision was made on those numbers. |

The rules existed. They were only spoken, so nothing could check them.

**Better models make this worse, not better.** A stronger model can work out what is *right*.
It cannot work out what *you decided*, and the longer it runs on its own, the further one
wrong premise goes before anyone notices.

The long version, with more examples and what stays with people:
[`docs/problem.md`](docs/problem.md).

## What Toprope does

1. **Declare the domain.** Objects, actions, who may do what in which state (a transition
   matrix), and rules that must always hold (invariants). An agent drafts it from your code,
   docs and an interview; the owner answers plain questions such as *"Can someone approve an
   experiment that is already running?"* and confirms. Agents propose; people decide.
2. **Check every change before it ships.** A change to the declaration is a commit with an
   impact report in domain terms (*"changes 2 cells; affects 14 tests, 1 invariant"*), checks
   for broken references, conflicting rules and regressions, what past events would have done
   under the new rules, and a preview to try. A person approves it. This is CI for rules.
3. **Generate what people and agents use.** MCP tools, a command line, a guide and a harness
   come from the same declaration, so everyone acts on the same meaning. The harness tests
   every state × action × role cell, not just a call graph.
4. **Refuse what is not allowed, and record everything.** Every action goes through one gate
   that checks the declaration and refuses with the declared reason. Actions, denials and
   decisions land in an event log, so the next change can be proposed from evidence.

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

The bet underneath: nobody defines a domain correctly in one go, so changing it must be cheap
and safe; and once it is declared precisely, writing the code is nearly free. How the pieces
fit: [`docs/how-it-works.md`](docs/how-it-works.md).

**It is not** an agent framework (use the agent you have), a guardrail product (enforcement
follows from the model; it is not the goal), or a hosted service. It fits where there is state,
allowed actions and rules, and poorly where there is little to declare.

## What is proven so far

Toprope is built as a chain of claims, each tested by a milestone with a preregistered verdict
([`docs/charter.md`](docs/charter.md)). Toprope's own authoring and delivery workflows are
already declared domains, and their tools are generated from those declarations; only the
kernel is hand-built. That shows the approach can be built. It does not yet show it is better.

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
| see how it works | [`docs/how-it-works.md`](docs/how-it-works.md), then [`docs/domain-model.md`](docs/domain-model.md) |
| understand the design and its claims | [`docs/charter.md`](docs/charter.md) (problem, claim chain, hypotheses, principles), [`docs/architecture.md`](docs/architecture.md) |
| use it | [`docs/workflow.md`](docs/workflow.md) (who runs what, when), [`docs/kernel-commands.md`](docs/kernel-commands.md), [`docs/server.md`](docs/server.md) |
| write a declaration | [`docs/domain-schema.md`](docs/domain-schema.md), [`docs/semantics.md`](docs/semantics.md) |
| follow the project | [`docs/STATUS.md`](docs/STATUS.md), [`docs/roadmap.md`](docs/roadmap.md), [`docs/experiments/M1-self-compile.md`](docs/experiments/M1-self-compile.md), [`docs/adr/`](docs/adr/) |
| contribute | [`AGENTS.md`](AGENTS.md): branch from `develop`, PR into `develop`, name the link your change serves |

Working notes in Korean: [`notes/ko/`](notes/ko/).

## License

Not chosen yet. The repository stays private until M1 has a verdict. Apache-2.0 is the
proposal (ADR-0005).
