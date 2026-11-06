# ADR-0038: The M1 binding joins the self-domain instrument exception

- Link: ① iterate safely, ⑥ org productivity (pilot only) · Status: accepted · 2026-11-06 ·
  decided by: SteamShon (option "B"; drafted by the assistant)
- Amends: ADR-0034 §3 (which M1 instruments an agent may draft), AGENTS.md (the exception),
  `experiments/m1/README.md`

## Context
ADR-0034 §3 lets an agent draft the self domains' M1 instruments when the researcher asks,
with multiple-choice options the researcher selects from: the probe suite, the change
requests, the change key and the verdict rules. It does not name the **binding**, the file
that maps each change request (and its key entry) to element names in the Phase A model,
written after Phase A and frozen before any arm runs. So the binding stayed human-only.

The reason ADR-0034 gave applies to the binding unchanged. M1 gives no link verdict; its ①
and ⑥ numbers are a pilot that tunes the checks and sizes M2. The binding adds no new
judgment on top of the key: it names, in the model's own vocabulary, what each already
frozen intent and key entry is about.

## Decision
1. **The M1 binding is part of the exception.** For the self domains' M1 binding, an agent
   may draft its content when the researcher asks, including options where an intent could
   bind to different elements. The researcher reviews, selects and freezes it in their own
   commit (`freeze-binding`), before any arm runs.
2. **Unchanged:** the binding is frozen before the pilot runs; it is not shown to any arm;
   the human-only rule stays for everything that feeds a link verdict (M2 and later
   instruments, including their bindings, and any gold set).

## Consequences
- The binding can be drafted from the frozen change requests and key and the approved
  self-domain commits, and the pilot can start once it is frozen.
- An agent that drafts the binding knows the key. ADR-0034 already accepts that for the
  drafting agent; the arms still never see the key or the binding.
