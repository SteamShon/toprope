"""The M1 instrument validator (experiments/tools/instruments.py), on placeholder copies of
the templates only. No gold content is written here: questions are format filler."""
import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INST = ROOT / "experiments/m1/instruments"
spec = importlib.util.spec_from_file_location("instruments", ROOT / "experiments/tools/instruments.py")
instruments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(instruments)


def filled(tmp_path, gold_items=None, domains=("toprope-authoring", "toprope-delivery"), compositions=None):
    for f in ("probe-suite", "change-requests", "change-key", "verdict-rules"):
        text = (INST / f"{f}.template.yaml").read_text()
        (tmp_path / f"{f}.yaml").write_text(re.sub(r"<[^>]*>", "filler", text))
    gold = yaml.safe_load(re.sub(r"<[^>]*>", "filler", (INST / "gold-scenarios.template.yaml").read_text()))
    gold["domains"] = list(domains)
    if compositions is not None:
        gold["compositions"] = list(compositions)
    if gold_items is not None:
        gold["scenarios"] = [{"answer": {"kind": "yes_no", "expected": "yes"}, "question": "filler", **x}
                             for x in gold_items]
    (tmp_path / "gold-scenarios.yaml").write_text(yaml.safe_dump(gold, sort_keys=False))
    return tmp_path


def run(d, capsys):
    errs = instruments.validate(d)
    return errs, capsys.readouterr().out


def test_items_name_one_of_the_files_domains(tmp_path, capsys):
    errs, _ = run(filled(tmp_path, [{"id": "A1", "domain": "toprope-authoring", "held_out": True},
                                    {"id": "X1", "domain": "billing", "held_out": False}]), capsys)
    assert errs == ["gold X1: domain must be one of ['toprope-authoring', 'toprope-delivery', 'toprope-self'] "
                    "(domains, then compositions)"]


def test_copies_of_a_fact_share_held_out(tmp_path, capsys):
    errs, _ = run(filled(tmp_path, [
        {"id": "A1", "domain": "toprope-authoring", "fact": "request-contents", "held_out": True},
        {"id": "D1", "domain": "toprope-delivery", "fact": "request-contents", "held_out": False}]), capsys)
    assert errs == ["gold fact 'request-contents': copies ['A1', 'D1'] must all be held out or all shown"]


def test_fact_key_warnings_and_per_domain_ratio(tmp_path, capsys):
    items = [{"id": "A1", "domain": "toprope-authoring", "fact": "f", "held_out": True},
             {"id": "A2", "domain": "toprope-authoring", "fact": "f", "held_out": True},
             {"id": "A3", "domain": "toprope-authoring", "fact": "lone", "held_out": False},
             {"id": "D1", "domain": "toprope-delivery", "held_out": True},
             {"id": "D2", "domain": "toprope-delivery", "held_out": True}]
    errs, out = run(filled(tmp_path, items), capsys)
    assert errs == []
    assert "asked twice of the same domain ['A1', 'A2']" in out
    assert "gold fact 'lone': only one item" in out
    assert "gold toprope-delivery: 2/2 held out" in out



def test_a_fact_spanning_domains_names_the_composition(tmp_path, capsys):
    item = {"id": "S1", "domain": "toprope-self", "held_out": True}
    errs, _ = run(filled(tmp_path, [item], compositions=["toprope-self"]), capsys)
    assert errs == []
    errs, _ = run(filled(tmp_path, [item], compositions=[]), capsys)
    assert errs and "domain must be one of" in errs[0]
    errs, _ = run(filled(tmp_path, [item], compositions=["toprope-authoring"]), capsys)
    assert errs == ["gold: ['toprope-authoring'] listed as both a domain and a composition"]


def test_an_all_shown_correctness_set_draws_no_held_out_warning(tmp_path, capsys):
    items = [{"id": f"A{i}", "domain": "toprope-authoring", "held_out": False} for i in range(4)]
    errs, out = run(filled(tmp_path, items), capsys)
    assert errs == [] and "held out" not in out
