# The problem: decisions live in people's heads

Link: P0, ⑥ (the problem Toprope starts from). The short version is in the
[README](../README.md). This page is the long one. The design is in [`charter.md`](charter.md),
and how it works is in [`how-it-works.md`](how-it-works.md).

## Code has a PR. Rules do not.

Nobody changes production code by editing it in place. You open a proposal, someone reviews it,
and it lands only once it is approved. There are three reasons: the change is seen before it
happens, it is recorded who accepted it, and from then on it is the reference everything else
is checked against.

Most of a company's other decisions have no such path. Put changing a payment system's code
next to changing a rule that system follows:

| | Changing the code | Changing a rule |
|---|---|---|
| Proposal | open a PR | none: changing it is applying it |
| What it changes | the current code (the base branch) | unknown: nobody can say what is decided now |
| What says it is right | types, linters, tests | the approver's memory |
| Machine checks first | CI | none: a person reviews everything from scratch |
| Lands without approval | no | yes |
| After it is accepted | it is the code; the next run reads it | nothing is left behind |

The second row decides the rest. With no base there is no diff, so there is nothing to
propose, check or approve. That is also why an approval step alone does not help: if what is
right lives only in the approver's head, the approver has to check everything, and nobody else,
person or agent, can check it for them. In code, CI checks first and the reviewer looks only at
what CI cannot see. Business rules have no CI, because nothing machine-readable says what is
right.

## Agents remove the half that was in people's heads

Every system's safety has two halves. One half is in the machine: permissions, input
validation, payment processing. The other half was in people's heads: *"Don't do that today,
you touched it yesterday."*

An agent replaces the person. The machine half stays, and the half that person carried leaves
with them. That half is the decisions.

Ask an agent to register a campaign on a large public ad platform and it can do it. Ask it to
do the same on an in-house ad system with almost the same data structure, and it cannot. The
model is the same. The difference is that the platform wrote its rules down and the in-house
system did not.

Execution logs are everywhere. Decision records are not. A system can keep a perfect history
of what ran and still not know whether the job it is about to rerun is allowed today.

## Rules that existed only as speech

| Domain | What was decided | What happened |
|---|---|---|
| Payments | "This promotion is refundable for 7 days only." | Support made one exception, and it became the custom. Nobody knows which is right now. |
| Ad delivery | "This campaign is a holdout: don't touch its budget." | Another team raised the budget while optimizing. The money was already spent. |
| Experiments | "A device, once assigned, never changes group." | It had been broken for three weeks when someone noticed, after a decision was made on those numbers. |
| Messaging | "No resend of the same campaign within 24 hours." | The same person got it three times. The button was pressed once. |

Every rule in the middle column is a quote. The rules existed; they were only spoken. None of
these is fixed by writing better code, because the code had nothing to check against.

## Writing it down does not fix it

The natural answer is a wiki page, or a few more lines in `AGENTS.md` or a skill. Three things
go wrong.

- **A document does not know whether it is still true.** A page written three months ago cannot
  tell you whether it still holds, and nothing breaks if nobody reads it.
- **Copies drift.** A rule copied into the payment server, the customer screen, the admin tool,
  settlement, the support script and the agent's prompt is six copies, and none of them is the
  original. Fix one and five stay silently wrong. Databases have had a name for this since 1970:
  the *update anomaly*. With four rules and six places that must follow them, that is 24
  hand-maintained links. With the rules declared in one place that the six ask, it is 4 + 6 = 10,
  and a change is made once.
- **Prose cannot be checked.** Add a line to a skill and nothing tells you whether it conflicts
  with the lines already there. You find out after deployment, from the result.

## Recording cannot be forced; it has to be the path

"How do we make people record their decisions?" has no answer. Recording that is separate from
the work always loses to urgent work. Meeting notes, wikis and policy documents all died that
way. Nobody asks how to force people to submit receipts, though: without a receipt, no money
comes out. The difference is not discipline. It is the path.

So the only working designs are ones where the work cannot proceed without the declaration:

- the system **asks** the declaration before acting, and with no answer it does not act;
- when something is blocked, the only way through is to declare it, so the record is made
  inside the work;
- **an exception is a recorded action**, not a side door;
- a change cannot **silently overwrite** an earlier decision: the conflict goes to a person;
- the cost of declaring is low: the owner **answers questions and confirms**, rather than
  writing a document.

## The pattern already works elsewhere

A thermostat holds a declared value (26°) and keeps comparing it with the room (28°).
Infrastructure-as-code declares "three servers" and refuses a stale plan. A type checker
refuses to build when the code disagrees with what was declared. In each case the declaration
is machine-readable, so a loop can compare it with reality and refuse what does not match.

Business rules are the one box left empty, because they are written in prose. No loop can run
on something that was never declared.

## Better models make this worse, not better

A stronger model can work out what is *right*. It cannot work out what *we decided*. Whether a
refund on day 8 is allowed depends on whether we set the window at 7 days or 30, and if we
never decided, that fact exists nowhere.

As models get stronger they remember more, use more tools and run longer on their own. One
wrong premise now turns into far more work before anyone notices, and the place where an agent
used to stop and ask gets skipped. Approval points are not needed because models are weak.
They are needed more as models get stronger.

## What stays with people

The goal is not to remove people. It is to decide where they stay.

| The system holds | People keep |
|---|---|
| the order of steps: none can be skipped | what this domain should mean |
| no one approves their own change | which decisions to declare at all |
| nothing closes without its evidence | whether partial coverage is acceptable |
| what is unknown is not folded into what is known | what counts as a domain in the first place |

An agent can do every step that proposes. It owns none of the steps that decide.

## What this asks of a solution, and what Toprope does

| The problem asks for | Toprope (design; see [Claim status](../README.md#claim-status)) |
|---|---|
| a base to diff against | the domain is a declaration: objects, actions, a transition matrix, invariants |
| CI for rules | every change gets an impact report and checks for breakage and conflicts, plus a preview, before deploy ([`change-check.md`](change-check.md)) |
| the declaration as the path, not a side record | agents and people act through MCP, a command line and UI generated from the declaration; anything not allowed is refused with a reason |
| low cost to declare | an interview turns undecided cells into plain questions; the owner answers and confirms |
| no silent overwrite, a record of who accepted what | an event log of every action, denial and decision; changes are commits that a person approves |

Whether this works is what the milestones test. Nothing here is measured yet.
