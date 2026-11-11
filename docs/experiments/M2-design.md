# M2: the first ① verdict, on the researcher's paper trading (design draft)

Link: ① iterate safely and ③ works as built, judged here; ② the model is right, observed only (ADR-0054). **Status: draft.**
The assistant drafted this at the researcher's request, carrying M1's findings into M2's
Phase B. The researcher decides each point and freezes it in M2's spec PR. The roadmap
(`roadmap.md`, M2) and ADR-0054 give the domain and the roles. This draft adds only what M1 changes.

**What stays human-only.** M2 gives link verdicts, so its instruments are written by people
(AGENTS.md):
- the change requests and their key;
- the binding;
- the probes;
- any gold set.

This draft holds none of them. Where it proposes verdict rules, they are a draft for the
researcher to review and freeze before any check is built.

## The question to preregister
M1 found the full Toprope arm level with an LLM reviewing the structured spec on recall (0.84
each, in one sitting), and both ahead of the natural-language skill (0.64). The compiler's own
share was a kind of problem no LLM review caught (M1-report). So M2 asks:

> **Does the full Toprope check beat a structured spec reviewed by an LLM, in both recall and
> precision, on changes whose problems a person who is not the builder seeds?**

If it does not, Toprope's value narrows to its declaration format, and to the kinds of problem only
the compiler catches. That is reported as such.

## Arms
All arms use the same model, the same frozen prompts and the same information (the design's
"second reader" check).

| Arm | Material | Pre-deploy check |
|---|---|---|
| NL skill | SKILL.md and examples, rendered blind from the declarations | an LLM review, 5 runs |
| Structured spec | the declarations and scenarios, as text | the same LLM review, 5 runs |
| **Toprope** | the declarations, scenarios and generated tools | its whole change check: structural, semantic, scenarios, harness, TLC, log replay, in-flight, `capability` (ADR-0048), outcome rules, and the `nl` check reading the compiler's view (5 runs) |

New in M2:
- **The Toprope arm is the product, not the compiler alone.** M1's first scoring measured the
  compiler alone, and the fair comparison came after.
- **The same edit is checked both ways.** In M1, the arms' edits differed, and the Toprope edits
  were worse (14 of 20 implemented the request). M2 proposes that each change be made once, by
  one editor, in the Toprope tools (with `propose_patch` and `check_draft`), and rendered into the
  other arms' materials. Then the arms differ only in their check. Recall is also reported on the
  changes every edit implemented.

## Measures (drafts; the researcher decides)
- **Recall and precision** per run, with mean, minimum and maximum, as in M1.
- **Precision two ways:** one flag at a time, and grouped (the report's `groups`; what the base
  carried left out). The grouped one is primary, since M1's ungrouped precision was dominated by
  one check's repetition.
- **Two noise floors:** the reviews' spread, and the grader's. M1's grader moved recall by about
  0.1 between sittings, and by 0.18 in the M1 recheck. The grader is redesigned before M2 so that
  no person adjudicates grades after the results: options, a recommendation and the decisions
  left are in [`M2-grader.md`](M2-grader.md) (draft).
- **Probes:** a probe counts only if it passes, in most runs, before any change in every arm.
  Each arm gets the same power for the same task (M1's `probe-baseline-findings.md`).
- **Iteration time**, edit to validated preview, with its limiter, as in M1.

## Verdict rules (draft, to be reviewed and frozen by the researcher)
They start from M1's `verdict-rules.yaml`, with three changes:

```yaml
iterate:
  supports:
    toprope_recall_min: 0.80
    toprope_precision_grouped_min: 0.70        # grouped precision, the primary one
    nl_recall_gap_min: 0.20                    # M1 measured 0.20 with the full arm (at the noise floor)
    structured_recall_gap_min: 0.10            # the compiler's contribution, the preregistered question
    structured_precision_grouped_gap_min: 0.0  # and not worse precision than the structured spec
    median_iteration_minutes_max: 1
  weakens:
    structured_within: 0.0                     # no recall gain over the structured spec
    toprope_precision_grouped_below: 0.50
  noise:
    gap_within_noise_is: inconclusive          # a gap within the larger noise floor decides nothing
```

What changed from M1, and why:
- **The gap to NL is 0.20, from 0.30.** M1 measured 0.20 with the full arm. The researcher may keep 0.30.
- **Precision is grouped.**
- **A gap within the noise floor is inconclusive,** rather than only marked. In M1 the rule was to
  mark such a gap but still apply the frozen thresholds (Decision 1).

## Before the run
1. **The roles (ADR-0054).** The researcher, as expert and owner, writes the change requests.
   A person who is not the builder seeds the problems and keeps the key. ② is observed, not
   judged. ADR-0054's open questions (the paper-trading API, how the tool reaches it, who places
   an approved order, who seeds) are decided in M2's spec PR.
2. **Freezing order.** The researcher freezes the probes, the verdict rules and the run protocol
   before the checks are built.
3. **Outcome rules in the domain.** The domain declares its outcome rules, through its interview
   (ADR-0048 §4), before the change sequence starts.
4. **A dry run.** It runs on two changes, as in M1.
