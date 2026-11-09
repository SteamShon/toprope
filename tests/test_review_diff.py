"""A person confirms a change from one readable diff (ADR-0049, B5)."""
import sys
from pathlib import Path

import pytest
import yaml
from test_decl import schema_doc_domain

from toprope.adapters.cli import main
from toprope.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import human_request as hr  # noqa: E402


def workspace(tmp_path) -> Workspace:
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(
        {"domain": "d.domain.yaml", "sources": [{"id": "docs", "kind": "records", "path": "docs"}]}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\nEngineers start an experiment by hand.\nA Note is free text.\n")
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    return Workspace(tmp_path)


def test_nothing_proposed_says_so(tmp_path):
    assert workspace(tmp_path).render_review() == "Nothing is proposed: there is nothing to confirm.\n"


def test_the_review_shows_each_proposal_against_main_with_its_source(tmp_path):
    ws = workspace(tmp_path)
    c0 = ws.commit()["commit"]
    ws.approve_commit(c0, via="terminal", who="ana")
    ref = ws.chunks("docs")[0].ref
    ws.propose("actions.launch_experiment.description", "Start it by hand.", ref,
               quote="Engineers start an experiment by hand.")
    ws.propose("objects.Note", {"description": "Free text."}, ref)
    items = {i["path"]: i for i in ws.review()}
    assert items["objects.Note"]["before"] is None                       # new
    assert items["actions.launch_experiment"]["before"]["description"] == "Start traffic to an approved experiment."
    assert items["actions.launch_experiment"]["now"]["description"] == "Start it by hand."
    assert "source" not in items["actions.launch_experiment"]["now"]     # a person reads the element, not its provenance
    text = ws.render_review()
    assert f"2 proposed element(s), against main {c0}:" in text
    assert f"+ objects.Note    (from {ref})" in text
    assert f"~ actions.launch_experiment    (from {ref})" in text
    assert '    "Engineers start an experiment by hand."' in text
    assert "    - description: Start traffic to an approved experiment." in text
    assert "    + description: Start it by hand." in text


def test_before_the_first_approval_every_element_is_new(tmp_path):
    ws = workspace(tmp_path)
    ws.propose("objects.Note", {"description": "Free text."}, ws.chunks("docs")[0].ref)
    assert "against main (none yet: every element is new)" in ws.render_review()


def test_toprope_run_review_prints_it(tmp_path, capsys):
    ws = workspace(tmp_path)
    ws.propose("objects.Note", {"description": "Free text."}, ws.chunks("docs")[0].ref)
    main(["--no-config", "--domain", str(tmp_path / "d.domain.yaml"), "--workspace", str(tmp_path), "review"])
    assert "+ objects.Note" in capsys.readouterr().out


def test_review_without_a_workspace_names_the_fix(tmp_path):
    ws = workspace(tmp_path)
    with pytest.raises(SystemExit, match="review needs the authoring workspace. Fix: give --workspace"):
        main(["--no-config", "--domain", str(ws.root / "d.domain.yaml"), "review"])


def test_a_person_sees_the_diff_before_confirming_on_the_terminal(capsys, monkeypatch):
    from toprope.adapters import cli
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    from toprope.identity.git import GitIdentity
    ident = GitIdentity.__new__(GitIdentity)
    caller = type("C", (), {"actor": type("A", (), {"kind": "person", "id": "ana"})()})()
    with pytest.raises(SystemExit, match="not taken"):
        cli._confirm_on_terminal(ident, caller, "confirm_all_proposed", "d", preface="+ objects.Note")
    assert "+ objects.Note" in capsys.readouterr().out


def test_the_human_request_page_shows_what_a_confirm_step_confirms(tmp_path):
    ws = workspace(tmp_path)
    ws.propose("objects.Note", {"description": "Free text."}, ws.chunks("docs")[0].ref)
    req = hr.change("d", workspace=str(tmp_path / "toprope.workspace.yaml"))
    page = hr.render(req)
    assert "#### What `confirm_all_proposed` confirms" in page and "+ objects.Note" in page
