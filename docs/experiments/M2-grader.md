# M2's grader: a redesign, drafted for the researcher

Link: ① ② (M2's verdicts), and none for the tooling. Status: **decided** (2026-11-10, the researcher: "추천대로 진행해줘"), not built yet. The chosen
parts are implemented, validated as *Validation* says, and frozen in M2's preregistration before
M2's main run. Context: [`M1-recheck.md`](M1-recheck.md), criterion 3 and its amendments;
[`M2-design.md`](M2-design.md).

## The problem

The grader decides whether a flag "identifies the seeded problem". In the M1 recheck it graded
the combined run twice, and each arm's recall moved by up to 0.18 between the two sittings. M1's
own report saw about 0.1. Most disagreements fall between `seeded` and `other-real`. Comparing a
free-text finding with a free-text key entry is itself ambiguous, so the noise sits in the
question, not in a person's attention. Asking a person afterwards did not help either: the
researcher could not decide a borderline case.

M2's verdicts compare Toprope with an NL skill and a structured spec. A grader noise of 0.1 to 0.2
is as large as the differences M2 has to see. So the grader must be steadier **before** M2 runs,
and no step may ask a person to adjudicate grades after the results are in.

**Goal:** the same run, graded twice, gives each arm's recall within a preregistered limit. This
draft proposes 0.05, and the limit is the researcher's to set. **Non-goals:** changing M1's
numbers or conclusions; tuning anything to M1's key or to the content of M1's disagreements.

## Options

### 1. Structured reviewer output, matched mechanically
Every finding carries fields: `kind` (conflict, breakage or other), `type` (the key's list:
conflicts-with-rule, breaks-reference, ...) and `against` (the rule, action or element it
conflicts with or breaks, by name). A script compares them with the key entry's `problem`,
`type` and `against`, as Toprope's compiler flags are already matched to the binding today.

- **For:** no grader noise where the fields match, and the reasons can be audited.
- **Against: it changes the arms.** The reviewer is asked to name what a finding is against. That is
  an ordinary thing for a domain owner to ask, but it also cues the reviewer to look for
  conflicts, which can raise every arm's recall. That cue is the same for every arm, but it is not
  the same in effect:
  - The structured and Toprope arms have rule and element names to cite.
  - The NL skill's rules are prose, so the NL reviewer has fewer names to give.
  - An NL finding that is right but unnamed would then miss the mechanical match.
- **Against: free text still needs reading.** `against` is free text, so matching it needs
  normalisation or a narrow grader question (option 2) anyway.
- **Validation:** it changes what the arms produce, so existing runs cannot validate it. It needs
  M2's pilot (*Validation*).

### 2. A checklist of narrow judgements instead of one broad one
For each flag, the grader answers yes or no to fixed items, each against the key entry:

- (a) Does the finding name the same rule, action or object as the key's `against`, or one that
  stands for it?
- (b) Does it say that the change conflicts with it or breaks it?
- (c) Does the outcome it describes violate that rule? This holds even when the finding presents
  the outcome as a gap in the implementation (rule B, option 4).

A preregistered formula then gives the label: `seeded` = (a) and ((b) or (c)). Real problems that
are not the seeded one are kept apart by a separate item, and false alarms by another.

- **For:** each item is narrower than "is this the seeded problem?", so two sittings agree more
  often. A disagreement points to one item, not to the whole judgement. The arms are not changed.
- **Against:** more grader output per flag. The items and the formula must be fixed before M2,
  with examples that do not come from M1.

### 3. Repeated grading, decided by majority
Every judgement (a label, or each checklist item) is graded k times, and the majority wins. The
draft proposes k = 3, with ties impossible for a binary item. k and the tie rule are
preregistered.

- **For:** it lowers the variance of a single sitting without asking anyone, and it combines with
  option 2.
- **Against:** k times the grading cost. M1's recheck cost about $23 per sitting for 5,160 flags.
  Two grouping steps cut this:
  - Identical compiler flags in one change are graded once.
  - Only flags that no script matched go to the model.

### 4. A fixed reading for borderline cases
The researcher's **rule B**: if the outcome a finding describes breaks the seeded rule, the finding
is `seeded`, even when it is phrased as a gap in the implementation. The rule goes into the grader
prompt and into checklist item (c), with a few written examples of a pass and a fail. The examples
are invented for the purpose. They are not taken from M1's key or from its graded flags.

- **For:** the commonest ambiguity is decided once, in advance.
- **Against:** none of note. Without it, options 2 and 3 only make the same ambiguity consistent at
  random.

### 5. A noise limit, checked before the main run
Before M2's main run, the grader is run twice on a calibration set, and each arm's recall must
differ by at most the limit. The calibration set is M2's pilot run (*Validation*). If the
difference is larger, the grader is changed and checked again. A preregistered cap is proposed:
two revisions. Only after it passes is the grader frozen and the main run started. The main run is
graded twice as well, and its noise is reported. A main run over the limit is reported as such:
nobody adjudicates it, and its verdicts are marked.

## Validation

- **Grader-only options (2, 3, 4).** Grade M1's existing combined run (`runs/phase-b-recheck-combined`)
  twice with the new grader. Do not run the arms again. Look only at **consistency**:
  - per-arm recall difference between the sittings;
  - per-flag agreement, also per checklist item.

  Do not compare with M1's labels or with which changes were caught. Do not read the content of
  M1's disagreements to tune the prompt. M1's conclusions do not change. The key is opened only
  inside the harness, as now. Each revision is counted toward option 5's cap.
- **Reviewer-format option (1).** Existing runs cannot show it, because the arms would produce
  something else. Plan:
  1. M2's pilot runs on a few changes kept outside M2's main list. They are written by the domain
     expert, like the rest.
  2. The pilot measures how many findings fill the fields validly in each arm, and whether NL
     findings are matched less often than the others for the same kind of problem.
  3. It also measures the grader's noise with the new format.
  4. If the format makes the arms unequal, it is dropped and options 2 to 4 carry the grading.

## Recommendation

Take options 2, 3, 4 and 5 for M2. They change only the grader, so the arms stay as M1 ran them,
and they can be checked now on M1's runs, for consistency only. Treat option 1 as an M2 pilot item,
decided on the pilot's evidence. Its effect on the arms is the risk M2 can least afford, since M2
compares the arms.

## Decisions (the researcher, 2026-11-10: as recommended)

1. **Adopted now: options 2, 3, 4 and 5.** Option 1 (the reviewer's structured output) is decided in
   M2's pilot, on its evidence.
2. **Noise limit: 0.05 of recall per arm**; at most **2** revisions of the grader before it is frozen.
3. **k = 3** for the majority.
4. The checklist's items (a), (b), (c) and the formula `seeded = (a) and ((b) or (c))`, as above;
   rule B's wording as option 4 gives it. The invented examples are drafted with the
   implementation, and the researcher reviews them before the grader is frozen.
5. **Calibration:** M1's combined run, graded twice, for options 2 to 4 (consistency only); M2's
   pilot for option 1 and for the final check.

## Next: the implementation

1. A grader prompt for the checklist goes into `phase_b/prompts/`, next to `grade_change.md`, which
   stays as M1 used it.
2. The harness grades with it, by majority, grouping identical flags.
3. A test shows that one judgement graded k times takes the majority.
4. The grader is validated on M1's run as above, then frozen with M2's instruments.

## The validation run (on M1's combined run, consistency only)

The checklist grader is `grade --grader checklist` (k = 3 by default). From `experiments/m1`, two
sittings into their own directories, then their noise against M2's limit:

```bash
uv run python -m phase_b grade --model MODEL --out runs/phase-b-recheck-combined --grader checklist --into scoring-checklist-1
uv run python -m phase_b grade --model MODEL --out runs/phase-b-recheck-combined --grader checklist --into scoring-checklist-2
uv run python -m phase_b compare-gradings --out runs/phase-b-recheck-combined \
  --first scoring-checklist-1 --second scoring-checklist-2 --limit 0.05
```

Only `grader-noise.scoring-checklist-1.scoring-checklist-2.json` is reported: each arm's recall in
the two sittings, the largest difference and whether it is within 0.05. M1's own grades
(`scoring/`, `scoring-2/`) are not touched, and no number is compared with them. Over the limit,
the grader is revised and checked again, at most twice; each revision is its own PR.

