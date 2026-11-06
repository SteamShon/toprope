# print-loop spike (throwaway)

Link: none. This is a side experiment, unrelated to the toprope claim chain. It tests
whether an agent can take a demand signal (bestseller reviews) to a printable,
customizable product with checks and a cost estimate, before any printer is bought.
The full experiment guide (Korean) is published as an artifact; this file is the
runbook for the code.

## What it does

```
inputs/evidence.md   (review evidence)          -- agent reads
specs/*.yaml         (requirements + parameters) -- agent writes
design/*.py          (parametric CAD, build123d) -- agent writes once per product
pipeline/run.py      (build -> check -> slice -> cost -> render -> report)  -- automatic
results/             (STL, PNG, report.md/json; fit_log.csv is filled by a person)
```

Checks per variant: valid single solid; fits A1 and A1 mini beds; minimum wall; the tag
sits free in the pocket; the lip stops it falling out; the detents stop it sliding out
but are not too tight; the speaker window is large enough; the mount feature exists.
`tests/test_checks.py` proves each check fails when the matching defect is introduced.

## Run

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/), and PrusaSlicer on the PATH
(`apt install prusa-slicer`, or the app on macOS/Windows, used only as a command-line
estimator).

```bash
cd spikes/print-loop
uv sync
uv run python pipeline/run.py specs/airtag_holder.yaml   # exits 1 if any check fails
uv run pytest
```

## Add a variant

Add an entry under `variants:` in the spec (another strap width, another name) and rerun.
No code changes.

## Assumptions

- Printer: Bambu Lab A1, 0.4 mm nozzle, PLA. The slicer profile in `profiles/` only
  approximates it; print with Bambu Studio's own A1 + PLA Basic preset.
- AirTag: 31.9 mm x 8.0 mm (published). Measure a real tag before the first print.
- Costs in `pipeline/run.py` (`ECON`): PLA $20/kg, $0.30 per machine hour, 10% reprints.
