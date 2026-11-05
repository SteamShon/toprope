"""The domain guide: a readable account of a domain, generated from its declaration."""
import copy
import subprocess

import yaml

from test_decl import schema_doc_domain
from toprope.decl import Domain
from toprope.harness import run_harness
from toprope.worldmap.guide import build_domain_guide


def test_the_guide_covers_every_part_of_the_declaration():
    raw = schema_doc_domain()
    d = Domain.model_validate(raw)
    g = build_domain_guide(d)
    assert g.startswith(f"# Domain guide: `{d.domain}` (version {d.version})") and "Do not edit" in g
    for name in d.objects:
        assert f"**{name}**" in g
    for name in d.actions:
        assert f"`{name}`" in g
    for n, link in d.links.items():
        assert f"`{link.from_}.{n}`" in g
    assert "denied: Launch requires approval." in g and "**undecided**" in g          # the matrix
    assert "Undecided cells (1):** `Experiment.ended.launch_experiment`" in g
    assert "📝" in g and "running-has-approver" in g and "one tool per action" in g


def test_the_guide_follows_the_declaration_and_the_harness():
    raw = schema_doc_domain()
    raw["actions"]["launch_experiment"]["requires"] = "human"
    d = Domain.model_validate(raw)
    assert "`launch_experiment` 🔒" in build_domain_guide(d)
    g = build_domain_guide(d, run_harness(d, levels=("model",), explore_examples=5, races=False).to_json())
    assert "**Harness**: passes" in g


def test_preview_and_the_cli_write_the_guide(tmp_path):
    from toprope.deploy import LocalEnvironment
    p = tmp_path / "d.domain.yaml"
    p.write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    b = LocalEnvironment(tmp_path / "env").preview(p, examples=0)
    assert (tmp_path / "env" / "builds" / b.id / "domain-guide.md").read_text().startswith("# Domain guide")
    out = subprocess.run(["uv", "run", "--quiet", "toprope-worldmap", "--domain", str(p), "--out",
                          str(tmp_path / "wm.json"), "--guide", str(tmp_path / "guide.md")],
                         capture_output=True, text=True, timeout=120, check=False)
    assert out.returncode == 0 and "## Transitions" in (tmp_path / "guide.md").read_text()
