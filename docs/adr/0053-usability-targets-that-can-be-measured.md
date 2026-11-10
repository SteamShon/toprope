# ADR-0053: The usability program's targets, stated so they can be measured

- Link: none (an enabler: it restates ADR-0049's targets) · Status: **accepted**, 2026-11-10,
  decided by SteamShon ("추천대로": the recommendation on each open point; drafted by the assistant
  after the integrated review of the four usability umbrellas)
- Amends: ADR-0049 §5 (done when), §2 (F1). Builds on: ADR-0050 (approvals by risk)

## Context
ADR-0049 set five targets. After the four themes were built, an integrated review (2026-11-10)
walked the path an M2 expert would take and found that three targets cannot be checked as they
are written, and that one measures the wrong thing:

1. **F2's "first enforced rule, no YAML by hand"** is measured on a newcomer's path. That path is
   not named, and the one the docs give (`toprope-init` from a template, then `toprope-set`)
   cannot add a rule the template does not have. The newcomer writes YAML.
2. **"At least 80% of the questions in F2's interview offer choices."** F2's path from a
   template has no interview. On the authoring interview, the measured share was 0% with no
   effects, and 28% with effects. Open questions about purpose and cast need no choice. The
   choices sit on the matrix rows, which the stop rule mostly skips; they are missing where the
   rules are decided.
3. **F1's "one command and one approval".** The F1 tool counts kernel commands by actor. A
   human request runs about nine kernel steps as the person, inside one approval, so the
   measure reads about nine where the target means one. It has no window, so a re-measure mixes
   in the logs from before the change.
4. **"Refusals at most half the baseline."** Pre-gate failures are counted per approved
   change, and the baseline has none. The two numbers are not comparable.
5. **"Every error names its fix."** The scan covers seven modules. The gate's own refusals,
   which agents hit most, are outside it.

## Decision
1. **F2 is measured on one named path:** the README's first step → `toprope-init` (from a
   template, or from a sentence of prose) → the person's own rule, added by command → `toprope-try`
   shows it enforced → `toprope-run` enforces it on the store. "No YAML by hand" means no line of
   the declaration, the story or the tokens is typed by the person.
2. **The choice target is counted where rules are decided.** At least 80% of the questions whose
   answer becomes an enforced element (an action's actor or precondition, a rule, a matrix cell)
   offer choices with a recommendation. The measure is taken on F2's script, through the
   interview entry point the docs give (or after a template, when the path takes one). Questions
   about purpose and wording stay open and are not counted.
3. **F1 counts touches, not kernel commands.**
   - *Person touches per approved change* = approvals of human requests, plus commands by a
     person outside any approved request.
   - *Approvals per approved change*, split by risk (low, high), from the request records.
   - Both are measured over a window that starts when theme 1 merges.
   - The target is one touch and one approval for a low-risk change.
   - The same holds without GitHub: a local apply of a request with one confirmation counts as
     one approval.
4. **Refusals are per command.** The ratio is refusals and failed effects per command by a
   person or an agent. Pre-gate failures (recorded since D1b) are reported beside it, not inside
   it, until a later baseline has them on both sides.
5. **"Every error names its fix" covers all of `src/toprope/` and `tools/human_request.py`,**
   the gate's refusals included. The scan test enforces it. A refusal that only a person can
   resolve names the human request as its fix.

## Consequences
- Each restated target maps to one change already in progress or planned:

  | Target | Change |
  |---|---|
  | F1 | the F1 tool gains touches, approvals by risk, and a window |
  | errors | the scan widens to all of `src/toprope/` and `tools/human_request.py` |
  | F2 | rule kinds added by command; a reset of the try store |
  | choices | an interview entry point, with choices moved to where rules are decided |

- F2's operator run waits until the named path exists. Running it earlier measures a path the
  program has already decided to change.
- No claim status changes; ADR-0049's other decisions stand.

## Decided on the open points (2026-11-10)
1. **A prose start is part of this program.** `toprope-init "<a sentence>"` starts a domain from a
   sentence, for a newcomer whose workflow matches no template. Its output is `proposed`, like any
   draft; a person confirms it.
2. **The 80% denominator is the questions whose answer becomes an enforced element.** These are
   an action's actor or precondition, a rule, or a matrix cell. Questions about purpose and wording
   are not counted.
