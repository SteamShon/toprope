# F2: time to a first enforced rule (ADR-0049)

Link: none (enabler). The script for ADR-0049's measure F2: from an empty directory to a first rule
the gate enforces. The baseline run uses the docs as they are when it runs. The end run uses the
docs and tools after the program, with the same script.

## Who runs it
- **The operator** has not used Toprope and has not read its code. Not the builder, and not an
  agent that has seen this repository. A different operator does the end run, so it does not
  measure what the first one learned.
- **The observer** records the times and counts below and does not help. The observer answers
  only "that is outside the task".
- The operator gets this page's *Task* section and a link to the repository's README, nothing
  else. They may use any coding agent they like; its commands count as the operator's touches
  only when the operator typed or approved them.

## Task (given to the operator as written)

> Your team handles expense claims. An employee submits a claim; a manager approves or rejects
> it. Your team decided two rules:
>
> 1. A claim over 1,000 needs a finance approver, not just a manager.
> 2. Nobody approves their own claim.
>
> Use Toprope so that an agent submitting and approving claims on your team's behalf cannot break
> these rules. You are done when you can show that the gate refuses an approval that breaks
> rule 1, with the rule's reason.

This workflow is not in `examples/`, so it cannot be copied whole.

## What the observer records

| Measure | How |
|---|---|
| minutes to done | from the first command or file opened, to the first refusal that names rule 1 |
| touches | commands the operator typed, plus approvals and confirmations they gave (an agent's own commands do not count) |
| hand-written YAML | lines of YAML the operator typed or edited themselves (a line pasted from the docs counts; a line an agent or `init` wrote does not) |
| stuck points | each time the operator stopped for more than 2 minutes, with what they were looking for |
| errors | each error message they met, and whether it told them what to do next |
| done | yes, or no after 90 minutes (record what was left) |

Record one row per run in the table below, with the commit of `develop` the run used.

### The choice measure (ADR-0053 §2)

Measured on the same run, through the interview entry point the docs give
([`docs/interview.md`](../interview.md)), with no extra step for the operator:

1. When the run is done (or stopped), the observer runs `toprope-interview <the operator's domain
   directory> --share`. It reads the interview log only.
2. It prints `questions` (those whose answer became an enforced element or could have: an
   action's actor, `requires` or precondition, an outcome rule, an invariant, a matrix cell,
   including those answered "none"; plus every refused or abandoned attempt at one), `offered`
   (those that offered choices with a recommended one), `share` (= offered ÷ questions), the
   declined, refused and abandoned counts, and the questions answered in open text (`open`).
3. The share does not show that the operator's rules hold. The observer also checks each of the
   task's rules is enforced: `toprope-harness` on the operator's declaration passes, and a
   command that breaks the rule is refused with its reason (`toprope-run` with the operator's
   tokens, or `toprope-try` on a story that tries it). A rule the operator stated that is not
   enforced is recorded under *stuck points*, with the question where it was lost.
4. Record `share`, and whether each rule is enforced (`1 ✓ 2 ✓`), in the *Choices* column below.
   The target is 0.8 or more, with every stated rule enforced. Questions about purpose and
   wording, and the question that names the actions, are not counted.

If the path goes through a template (`toprope-init --template`) and the operator never runs the
interview, record `n/a (no interview)`: the measure is taken only where the docs send the operator
to the interview. Dry runs on generic examples (leave requests; purchases with "over 2,500 needs a
director", not this task's text) with the recommended answers give 8 of 8 and 10 of 10, with the
stated limit enforced (`tests/test_interview_on_the_path.py`); they check the tool, they are not a
measurement.

## Runs

| Date | Run | `develop` at | Operator | Minutes | Touches | YAML lines | Choices | Done |
|---|---|---|---|---|---|---|---|---|
| | baseline | | | | | | | |

## The documented path today (not a run)

On `develop` as of 2026-11-09, the README offers no way to start a domain other than an example:
there is no `init` and no template. To finish the task, an operator must write a declaration and
an identity file by hand. The closest example, `examples/refunds/`, is a 29-line declaration and
a one-line token file. The authoring interview (`domains/authoring/guide.md`) can draft one, but
it is run through the self domains' composition, with four path options and a workspace file
on every command. So the baseline run is expected to take at least about 30 lines of hand-written YAML. That
is an expectation, not a measurement; the run decides.
