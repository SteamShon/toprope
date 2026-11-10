# Theme 2: getting started (ADR-0049)

Link: none (enabler for ② and ⑥: an expert who is not the builder starts here). The plan for
`umbrella/usability-start`, stacked on theme 1 (`umbrella/usability-change-loop`, #201) because
it uses `toprope.yaml`. It merges into `develop` after theme 1 does, once M1's recheck is in.
Progress is in [`STATUS.md`](../STATUS.md).

## Targets
Measured with F2's script ([`U-f2-first-rule.md`](U-f2-first-rule.md)):

| Measure | Today | Target |
|---|---|---|
| minutes to a first enforced rule | not measured; the docs offer no start | 30 or fewer |
| YAML lines written by hand | about 30 (a declaration and a token file) | 0 |
| commands before the first refusal is seen | several, assembled from two READMEs | 2 (`toprope-init`, `toprope-try`) |

## Sub-PRs, in order

| # | Item | Touches the self domains? |
|---|---|---|
| 1 | A3 + A4: a template library (approval, refund window, budget change, release, experiment); `toprope-init <name> --template T` writes a working domain (declaration, identities, `toprope.yaml`); `toprope-try` walks its scripted story and shows each refusal with its reason | no |
| 2 | Changing a template's rule without YAML: `toprope-init` asks for the template's parameters (a limit, a role, a window) and writes them; the change check shows what the change touches | no |
| 3 | E1: the README and docs lead with the first step (init, try, connect an agent), the rest one link away | no |
| 4 | E2: a 15-minute tutorial that runs as a test, so it never goes stale | no |

| 5 | F2's named path (ADR-0053), after the integrated review of 2026-11-10: an own rule added by command (`toprope-rule`, `toprope-add`, `toprope-rename`), `toprope-try --reset` and `--accept`, a prose start (`toprope-init "<a sentence>"`), the experiment template that row 1 named and #214 left out, and the README's install step and first-rule path | no |

None of these run the self domains' loop.

## Done when
Every row is done, the tutorial runs in CI, and F2's script can be finished with no YAML
written by hand on ADR-0053's named path (README → `toprope-init` → an own rule by command →
`toprope-try` → `toprope-run`; `tests/test_first_rule_path.py` walks it on a workflow of its own),
to be measured by an operator the researcher finds.
