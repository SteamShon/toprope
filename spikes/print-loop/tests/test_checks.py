"""The design checks must catch real defects, not just pass.

Each case breaks one thing in the spec and asserts the matching check fails.
Run: uv run pytest
"""

import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "design"), str(ROOT / "pipeline")]
import airtag_holder as design  # noqa: E402
import run  # noqa: E402

SPEC = yaml.safe_load((ROOT / "specs" / "airtag_holder.yaml").read_text())


def failing(spec: dict, variant_id: str) -> set[str]:
    v = next(x for x in spec["variants"] if x["id"] == variant_id)
    return {c["id"] for c in run.checks(spec, v, design.build(spec, v)) if not c["ok"]}


@pytest.mark.parametrize("variant_id", [v["id"] for v in SPEC["variants"]])
def test_spec_as_written_passes(variant_id):
    assert failing(SPEC, variant_id) == set()


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("detent_mm", 0.0, "R2 detents stop tag sliding out"),
        ("clearance_mm", -0.2, "R2 tag sits free in pocket"),
        ("lip_overlap_mm", 0.0, "R2 lip stops tag falling out the front"),
        ("detent_mm", 1.5, "R2 detent clicks (not too tight)"),
    ],
)
def test_broken_fit_is_caught(field, value, expected):
    spec = copy.deepcopy(SPEC)
    spec["fit"][field] = value
    assert expected in failing(spec, "keyring-blank")
