# The interview: declare your workflow by answering questions

Link: none (an enabler for ② and ⑥: the interview is how an owner's knowledge gets into a
declaration). The route a newcomer takes to describe their own workflow, without writing YAML
(ADR-0049, ADR-0053 §2). Progress is in [`STATUS.md`](STATUS.md).

## Run it

On a directory that holds a `domain.yaml` (one `toprope-init` wrote, or an empty one), with your
documents, if you have any, in a `sources/` folder next to it:

```
toprope-interview my-leave              # asks in the terminal
toprope-interview my-leave --answers answers.txt   # the same, one answer per line
toprope-interview my-leave --share      # the measure below, from the interview log
```

The first run writes `toprope.workspace.yaml` (the declaration is `domain.yaml`, the log
`interview/log.jsonl`, and the Markdown files in `sources/` are your sources). It never changes
a file you wrote except `domain.yaml`, and only with what you answered.

## What it asks, and how you answer

One question at a time, in the order the declaration depends on (ADR-0025): sources, purpose,
people and things, an example, actions, stages, rules, the world, handoffs, review.

- **Open questions** are about purpose and wording: what the problem is, who takes part, what the
  work tracks, what each action is called. Each shows the short form it takes, such as
  `role: what they do; role: what they do`.
- **Questions whose answer becomes a rule** offer numbered choices built from your draft, your
  example and your sources, one recommended with why. Press Enter for the recommended one, type a
  number for another. These are:

  | What is decided | Choices | Recommended from |
  |---|---|---|
  | who may take an action | each role, or the roles your words fit | the glossary's description of each role and the action's description |
  | who must not take it | only a person; not whoever made the thing (refused while who made it is unknown); both; anyone with the role | a source passage that says so ("Nobody approves their own request.") |
  | a limit on a number | over the stated value, only one role may; over it, nobody may; no limit | a number your words state ("over 1,000"), in a passage naming the fact, the thing or the action; otherwise **no limit**, the default |
  | what an action does in each stage | from any stage to the stage named after the action, refused elsewhere; refused everywhere; not applicable | the stage named after the action's verb (`paid` for pay), from the last stage before it that is not another decision's outcome; nothing is recommended when no stage is named after it |
  | an outcome rule (ADR-0048) | a stage needs a person, or one role | a source passage that says so |
  | cells nobody has tried yet | each as recommended, all refused, or left undecided | ADR-0014's fail-closed default |

  Where your words say nothing, the recommendation says so (for example, "anyone with the role",
  "no limit") rather than inventing a rule. You can also type the rule you mean at a limit
  question (`over 1,000, only finance`) or a stage question (`from submitted to approved`). An
  answer the interview cannot take is refused with its fix and the question is asked again; the
  session never ends on it.

Everything is written `proposed`. At the end the interview shows each proposed element, where it
came from, and what approving it decides, in your words; it confirms only when you type `yes`.

## An example session (abridged)

From `tests/interview/` (a team's leave requests, with a one-page policy in `sources/`):

```
[People and things] Who takes part? ...
  > employee: asks for time off; manager: approves or refuses requests; hr: approves long requests

[Actions] What does each role do, to which thing? ...
  > request_leave: Ask for time off -> new Leave request; approve_leave: Approve the request -> Leave request; ...

[Actions] Who may approve the request? (the action approve_leave, on a LeaveRequest)
  1. any of: manager, hr   <- recommended
       why: the glossary says the manager “approves or refuses requests”, as “Approve the request” says ...
  choice [Enter = 1]:

[Actions] Is there a limit on days before someone may approve the request? ...
  3. over 10 days, only the hr may approve the request   <- recommended
       why: your words say “A request over 10 days needs HR, not just a manager.” (sources:sources/policy.md#L1-L5)
  8. over 12 days, nobody may approve the request
  9. no limit on days
  choice [Enter = 3]:

Who does what (* proposed, not yet confirmed):
  roles: employee, manager, hr
  LeaveRequest*: days, created_by
  employee: request_leave* -> new LeaveRequest
  manager: reject_leave* -> LeaveRequest; approve_leave* -> LeaveRequest (a person only)
  hr: approve_leave* -> LeaveRequest (a person only)
...
  Confirm all of it? Type yes to confirm (anything else: not now): yes
```

The map (`Who does what`) is shown from the people and things on, and the stages of each thing
once it has them.

## The measure (ADR-0053 §2)

Of the questions whose answer became an enforced element, or would have (an action's actor,
`requires` or precondition, an outcome rule, an invariant, a matrix cell, including those answered
"none"), plus every refused or abandoned attempt at one, the share that offered choices with a
recommended one. Purpose and wording are not counted, nor is naming the actions (it names them;
their actors are chosen after). `toprope-interview DIR --share` prints it from the interview log,
with the declined, refused and abandoned counts and the questions answered in open text.

The share alone does not show that the rules the person stated are enforced: F2's procedure also
checks that (see [`experiments/U-f2-first-rule.md`](experiments/U-f2-first-rule.md)). The target is
80% or more on F2's script. With the recommended answers, the leave example gives 8 of 8, and a
purchase example in F2's shape ("A purchase over 2,500 needs a director") gives 10 of 10 with the
limit enforced: the harness and the gate refuse a team lead's approval over 2,500
(`tests/test_interview_on_the_path.py`).

## What it does not do yet

- A handoff, or an invariant beyond a `check | why` line, is drafted with your agent through the
  Authoring tools, not in the terminal.
- Guards and limits are offered for actions that let a thing go ahead (approve, pay, grant...)
  that the interview drafted; a template's actions, or ones you confirmed, are left as they are.
- Rules on a template come from `toprope-set` (theme 2); the interview asks only for what the
  draft lacks.
