"""Start a domain from a template and see its rules work (ADR-0049, A3 and A4)."""
import json

import pytest
import yaml

from toprope.adapters.cli import main as run, read_config
from toprope.adapters.cli.start import check, init, init_main, play, templates, try_main
from toprope.decl import load_domain, validate_domain
from toprope.harness import run_harness

TEMPLATES = sorted(templates())


def test_there_are_templates_for_the_common_workflows():
    assert {"approval", "budget", "refunds", "release"} <= set(TEMPLATES)


@pytest.mark.parametrize("name", TEMPLATES)
def test_every_template_is_valid_passes_its_harness_and_its_story(tmp_path, name):
    out = init(f"my-{name}", name, tmp_path)
    d = load_domain(out / "domain.yaml")
    assert d.domain == f"my-{name}"
    assert not [i for i in validate_domain(d) if i.severity == "error"]
    assert run_harness(d, levels=("model",), explore_examples=5, races=False).ok
    ok, rows = play(out)
    assert ok, [r for r in rows if not r["as_told"]]
    assert any(r["result"] == "denied" for r in rows)             # every story shows a refusal and why
    assert all(r["reason"] for r in rows if r["result"] == "denied")


def test_init_writes_a_domain_toprope_run_uses_with_no_other_option(tmp_path, monkeypatch, capsys):
    out = init("my-access", "approval", tmp_path)
    assert {p.name for p in out.iterdir()} >= {"domain.yaml", "tokens.yaml", "story.yaml", "toprope.yaml"}
    cfg = read_config(out / "toprope.yaml")
    assert cfg["domain"] == str(out / "domain.yaml") and cfg["store"] == f"sqlite:{out / '.toprope/events.db'}"
    monkeypatch.chdir(out)
    run(["submit_request", "R-wiki", "--token", "t-mia"])          # who you are may come last
    assert json.loads(capsys.readouterr().out)["state"]["status"] == "submitted"
    with pytest.raises(SystemExit):
        run(["approve_request", "R-wiki", "--token", "t-mia"])     # a member is no approver
    assert json.loads(capsys.readouterr().out)["status"] == "denied"


def test_try_prints_who_asked_what_and_why_it_was_refused(tmp_path, capsys):
    out = init("my-refunds", "refunds", tmp_path)
    try_main(["--dir", str(out)])
    text = capsys.readouterr().out
    assert "asks to refund an order from day 8" in text
    assert "denied: Refunds are allowed within 7 days of purchase." in text and "Next:" in text


def test_a_change_that_breaks_the_story_fails_try_and_check_reports_it(tmp_path, capsys):
    out = init("my-refunds", "refunds", tmp_path)
    decl = out / "domain.yaml"
    decl.write_text(decl.read_text().replace("<= 7", "<= 30"))
    with pytest.raises(SystemExit, match="a step did not end as the story says. Fix:"):
        try_main(["--dir", str(out)])
    assert "the story expected denied (within-window)" in capsys.readouterr().out
    assert "changes 1 precondition(s)" in check(out)


def test_a_check_written_as_a_bare_true_gets_a_readable_error(tmp_path):
    out = init("my-refunds", "refunds", tmp_path)
    decl = out / "domain.yaml"
    decl.write_text(decl.read_text().replace("check: target.days_since_purchase <= 7", "check: true"))
    with pytest.raises(SystemExit, match=r"a check is text: quote it.*Fix:"):
        play(out)


@pytest.mark.parametrize("args, says", [
    (["My Domain", "--template", "approval"], "is not a domain name. Fix:"),
    (["ok-name", "--template", "nope"], "no template 'nope'. Fix: use one of"),
    (["ok-name"], "no --template. Fix: choose one of"),
])
def test_init_refuses_with_the_fix(tmp_path, args, says):
    with pytest.raises(SystemExit, match=says):
        init_main([*args, "--dir", str(tmp_path)])


def test_init_never_overwrites(tmp_path):
    init("my-access", "approval", tmp_path)
    with pytest.raises(SystemExit, match="exists. Fix:"):
        init("my-access", "approval", tmp_path)


def test_a_config_with_a_domain_and_a_composition_is_refused(tmp_path):
    p = tmp_path / "toprope.yaml"
    p.write_text(yaml.safe_dump({"domain": "d.yaml", "composition": "c.yaml"}))
    with pytest.raises(SystemExit, match="both `domain` and `composition`. Fix:"):
        read_config(p)


@pytest.mark.parametrize("template, example, name", [
    ("refunds", "refunds/refunds.domain.yaml", "refunds"),
    ("budget", "paid-media/paid-media.domain.yaml", "paid-media"),
])
def test_the_examples_are_copies_of_their_template(template, example, name):
    """The templates are the source (src/toprope/templates/README.md); an example drifting from
    its template fails here, with the copy to make."""
    from importlib import resources
    from pathlib import Path
    root = resources.files("toprope.templates") / template
    examples = Path(__file__).resolve().parents[1] / "examples"
    want = (root / "domain.yaml").read_text().replace(f"domain: {template}\n", f"domain: {name}\n", 1)
    assert (examples / example).read_text() == want, \
        f"examples/{example} differs from the {template} template: copy the template's domain.yaml there"
    assert (examples / Path(example).parent / "tokens.yaml").read_text() == (root / "tokens.yaml").read_text()
