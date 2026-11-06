"""The command line generated from a declaration (ADR-0036), and the guide's how-to-work section."""
import json
import subprocess

import yaml
from test_decl import schema_doc_domain

from toprope.decl import Domain
from toprope.worldmap.guide import build_domain_guide


def setup(tmp_path):
    p = tmp_path / "d.domain.yaml"
    p.write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    ids = tmp_path / "ids.yaml"
    ids.write_text(yaml.safe_dump({"t-ana": {"id": "ana", "roles": ["approver"]},
                                   "t-eli": {"id": "eli", "roles": ["eng"]}}))
    base = ["uv", "run", "--quiet", "toprope-run", "--domain", str(p), "--store", f"sqlite:{tmp_path / 'e.db'}",
            "--identity", f"static:{ids}"]

    def run(*a, token="t-ana"):
        return subprocess.run(base + list(a), capture_output=True, text=True, timeout=120, check=False,
                              env={**__import__("os").environ, "TOPROPE_TOKEN": token})
    return run


def test_one_subcommand_per_action_with_the_declarations_rules(tmp_path):
    run = setup(tmp_path)
    helptext = run("--help").stdout
    assert "approve_experiment" in helptext and "launch_experiment" in helptext and "guide" in helptext
    assert "Who: eng" in run("launch_experiment", "--help").stdout                  # the declaration's words
    first = run("--seed", "launch_experiment", "E-onboarding", token="t-eli")       # draft: denied by the matrix
    assert first.returncode == 1 and json.loads(first.stdout)["code"] == "matrix"
    ok = run("approve_experiment", "E-onboarding", "--note", "fine")
    assert ok.returncode == 0 and json.loads(ok.stdout)["state"]["status"] == "approved"
    assert json.loads(run("get", "E-onboarding").stdout)["approved_by"] == "ana"
    assert "launch_experiment" in json.loads(run("allowed", "E-onboarding", token="t-eli").stdout)
    assert run("launch_experiment", "E-onboarding", token="t-eli").returncode == 0
    assert [e["type"] for e in json.loads(run("history", "E-onboarding").stdout)][-1] == "ExperimentLaunchExperiment"
    assert run("guide").stdout.startswith("# Domain guide")


def test_the_guide_says_who_does_what_in_each_stage():
    g = build_domain_guide(Domain.model_validate(schema_doc_domain()))
    part = g[g.index("## How to work in this domain"):g.index("## What is generated")]
    assert part.index("**In `draft`:**") < part.index("**In `approved`:**") < part.index("**In `running`:**")
    assert "- **approve_experiment** by `approver`" in part and "recorded as a decision" in part
    assert "Run: `toprope-run --domain example.domain.yaml launch_experiment ID`" in part
    assert "toprope-run" in g[g.index("## What is generated"):]
