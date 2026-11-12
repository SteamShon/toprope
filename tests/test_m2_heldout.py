"""experiments/tools/m2_heldout.py: M2's held-out items are checked and sealed without showing
their content. The items here are format filler, not gold."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m2_heldout", ROOT / "experiments/tools/m2_heldout.py")
ho = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ho)
SECRET = "filler-question-text-that-must-not-print"


def _filled(tmp_path, n=3):
    doc = yaml.safe_load((ROOT / "experiments/m2/heldout.template.yaml").read_text())
    doc["items"] = [{"id": f"H{i:02}", "question": f"{SECRET} {i}", "answer": {"kind": "yes_no", "expected": "no"},
                     "tacit": i % 2 == 0} for i in range(1, n + 1)]
    f = tmp_path / "heldout.yaml"
    f.write_text(yaml.safe_dump(doc, allow_unicode=True))
    return f


def test_the_template_itself_is_refused_until_filled(capsys):
    with pytest.raises(SystemExit):
        ho.cmd_validate(argparse.Namespace(file=str(ROOT / "experiments/m2/heldout.template.yaml")))
    assert "still the placeholder" in capsys.readouterr().out


def test_validate_prints_counts_never_content(tmp_path, capsys):
    ho.cmd_validate(argparse.Namespace(file=str(_filled(tmp_path))))
    out = capsys.readouterr().out
    assert "3 items, 1 tacit" in out and SECRET not in out


def test_format_errors_name_the_field_not_the_content(tmp_path, capsys):
    f = _filled(tmp_path)
    doc = yaml.safe_load(f.read_text())
    doc["items"][1]["answer"] = {"kind": "outcome", "expected": SECRET}
    f.write_text(yaml.safe_dump(doc))
    with pytest.raises(SystemExit):
        ho.cmd_validate(argparse.Namespace(file=str(f)))
    out = capsys.readouterr().out
    assert "item H02: an outcome answer expects" in out and SECRET not in out


def test_seal_records_only_the_hash_and_ids_and_unseal_checks_it(tmp_path):
    f = _filled(tmp_path)
    sealed, into = tmp_path / "sealed.json", tmp_path / "unsealed.yaml"
    ho.cmd_seal(argparse.Namespace(file=str(f)), sealed=sealed)
    rec = json.loads(sealed.read_text())
    assert rec["sha256"] == hashlib.sha256(f.read_bytes()).hexdigest() and rec["ids"] == ["H01", "H02", "H03"]
    assert SECRET not in sealed.read_text()
    with pytest.raises(SystemExit, match="sealed once"):
        ho.cmd_seal(argparse.Namespace(file=str(f)), sealed=sealed)
    f.write_text(f.read_text().replace("expected: 'no'", "expected: 'yes'", 1))   # an answer changed after sealing
    with pytest.raises(SystemExit, match="differs from the sealed one"):
        ho.cmd_unseal(argparse.Namespace(file=str(f)), sealed=sealed, into=into)
    assert not into.exists()


def test_seal_refuses_a_file_inside_the_repository(tmp_path):
    with pytest.raises(SystemExit, match="inside the repository.*Fix: keep the filled file outside"):
        ho.cmd_seal(argparse.Namespace(file=str(ROOT / "experiments/m2/heldout.template.yaml")),
                    sealed=tmp_path / "s.json")


def test_agents_are_denied_the_private_folder():
    deny = json.loads((ROOT / ".claude/settings.json").read_text())["permissions"]["deny"]
    assert {"Read(~/m2-private/**)", "Edit(~/m2-private/**)"} <= set(deny)
