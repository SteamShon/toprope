"""Harness mutants: each seeded break given to the execution level must be caught (a check never
seen failing proves nothing)."""
from pathlib import Path

import pytest
import yaml
from test_decl import schema_doc_domain

from toprope.decl import Domain, load_domain
from toprope.harness import Harness
from toprope.harness.cli import main as harness_cli
from toprope.harness.mutants import mutants, run_mutants

EXAMPLES = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*/*.domain.yaml"))


def test_every_operator_seeds_a_break_in_the_toy_domain():
    ids = [m.id for m in mutants(Domain.model_validate(schema_doc_domain()))]
    assert {i.split(":")[0] for i in ids} == {"skip-precondition", "skip-effect", "deny-cell", "retarget-cell",
                                             "allow-cell"}
    assert "skip-precondition:approve_experiment.has-guardrails" in ids and len(ids) == len(set(ids))


def test_the_unbroken_declaration_as_implementation_passes():
    d = Domain.model_validate(schema_doc_domain())
    assert Harness(d, levels=("model", "execution"), implementation=d).run(explore_examples=0, races=False).ok


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_the_harness_catches_every_mutant_of_the_examples(path):
    # Before boundary instances were made from the world, three survived: paid-media's step-limit
    # (it reads params) and not-the-proposer, and refunds.30-days's within-window.
    out = run_mutants(load_domain(path))
    assert out["survived"] == [] and out["total"] > 0


def test_a_mutant_no_state_can_tell_apart_survives_and_fails_the_cli(tmp_path, capsys):
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "always", "check": "true", "reason": "Always holds."})
    d = Domain.model_validate(raw)
    out = run_mutants(d)
    assert [m["mutant"] for m in out["survived"]] == ["skip-precondition:approve_experiment.always"]
    f = tmp_path / "d.domain.yaml"
    f.write_text(yaml.safe_dump(raw, sort_keys=False))
    with pytest.raises(SystemExit) as e:
        harness_cli(["--domain", str(f), "--mutants"])
    assert e.value.code == 1 and "survived skip-precondition:approve_experiment.always" in capsys.readouterr().out
