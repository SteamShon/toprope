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


def test_stage_one_needs_no_gold_file(tmp_path, capsys):
    """ADR-0031: M1 freezes the four ① instruments; a gold file is optional."""
    d = filled(tmp_path)
    (d / "gold-scenarios.yaml").unlink()
    assert instruments.validate(d) == []
    for f in ("probe-suite", "change-requests", "change-key", "verdict-rules"):
        p = d / f"{f}.yaml"
        p.write_text(p.read_text().replace("status: draft", "status: frozen"))
    assert instruments.freeze(d) == []
    import json
    assert sorted(json.loads((d / "FROZEN.json").read_text())["files"]) == [
        "change-key.yaml", "change-requests.yaml", "probe-suite.yaml", "verdict-rules.yaml"]
    assert instruments.verify(d) == []


def test_the_checks_wait_only_for_the_probes_and_verdict_rules(tmp_path, capsys):
    """ADR-0034: the probe suite and verdict rules gate the checks; the change requests and key
    are frozen later, before the pilot runs."""
    import json
    d = filled(tmp_path)
    (d / "gold-scenarios.yaml").unlink()
    later = {f: (d / f"{f}.yaml").read_text() for f in ("change-requests", "change-key")}
    for f in later:
        (d / f"{f}.yaml").unlink()
    assert instruments.validate(d) == []
    for f in ("probe-suite", "verdict-rules"):
        p = d / f"{f}.yaml"
        p.write_text(p.read_text().replace("status: draft", "status: frozen"))
    assert instruments.freeze(d) == []
    assert instruments.verify(d) == []                                   # the checks may be built
    assert any("change-requests.yaml" in e for e in instruments.verify(d, run=True))
    (d / "change-requests.yaml").write_text(later["change-requests"].replace("status: draft", "status: frozen"))
    assert instruments.freeze(d) == ["freeze the change requests and the change key together"]
    (d / "change-key.yaml").write_text(later["change-key"].replace("status: draft", "status: frozen"))
    assert instruments.freeze(d) == []                                   # the pilot's two, later
    assert sorted(json.loads((d / "FROZEN.json").read_text())["files"]) == [
        "change-key.yaml", "change-requests.yaml", "probe-suite.yaml", "verdict-rules.yaml"]
    assert [e for e in instruments.verify(d, run=True)
            if "binding" not in e and "run-protocol" not in e] == []          # frozen later, below


def test_a_frozen_file_can_be_amended_on_the_record(tmp_path, capsys):
    """A frozen instrument may change later: the old hash is kept in its history with the reason."""
    import json
    d = filled(tmp_path)
    (d / "gold-scenarios.yaml").unlink()
    for f in ("change-requests", "change-key"):
        (d / f"{f}.yaml").unlink()
    for f in ("probe-suite", "verdict-rules"):
        p = d / f"{f}.yaml"
        p.write_text(p.read_text().replace("status: draft", "status: frozen"))
    assert instruments.freeze(d) == []
    first = json.loads((d / "FROZEN.json").read_text())["files"]["verdict-rules.yaml"]["sha256"]
    p = d / "verdict-rules.yaml"
    p.write_text(p.read_text().replace("preview_seconds: 60", "preview_seconds: 45"))
    assert instruments.verify(d) == ["verdict-rules.yaml changed after freezing"]
    assert instruments.amend(d, "verdict-rules", "") == ["amend needs --reason: why the frozen file changes"]
    assert instruments.amend(d, "change-key", "x") == ["change-key.yaml is not frozen; use freeze"]
    assert instruments.amend(d, "verdict-rules", "the preview target was too tight") == []
    meta = json.loads((d / "FROZEN.json").read_text())["files"]["verdict-rules.yaml"]
    assert meta["history"][0]["sha256"] == first and meta["history"][0]["reason"] == "the preview target was too tight"
    assert instruments.verify(d) == []
    assert instruments.amend(d, "verdict-rules", "again") == ["verdict-rules.yaml is unchanged; nothing to amend"]
    p.write_text(p.read_text().replace("status: frozen", "status: draft"))
    assert any("keep status: frozen" in e for e in instruments.amend(d, "verdict-rules", "draft again"))


def test_the_run_protocol_is_frozen_by_hash_before_any_arm_runs(tmp_path, capsys):
    """The Phase B run protocol (Markdown) is frozen by its hash, after the four instruments, and
    `verify --run` needs it; a change after freezing goes through amend."""
    import json
    d = filled(tmp_path)
    (d / "gold-scenarios.yaml").unlink()
    for f in ("probe-suite", "verdict-rules", "change-requests", "change-key"):
        p = d / f"{f}.yaml"
        p.write_text(p.read_text().replace("status: draft", "status: frozen"))
    proto = d / "run-protocol.md"
    proto.write_text("# Run protocol\n\nStatus: **draft**.\n\nRun each reviewer 5 times.\n")
    assert instruments.freeze_protocol(d) == [
        "the instruments are not all frozen yet: ['probe-suite.yaml', 'verdict-rules.yaml', "
        "'change-requests.yaml', 'change-key.yaml']"]
    assert instruments.freeze(d) == []
    assert instruments.validate(d) == []                                 # Markdown is not validated as YAML
    assert instruments.freeze_protocol(d) == ["run-protocol.md: set status: frozen yourself before freezing"]
    assert "run-protocol.md is not frozen" in instruments.verify(d, run=True)
    proto.write_text(proto.read_text().replace("**draft**", "**frozen**"))
    assert instruments.freeze_protocol(d) == []
    assert "run-protocol.md" in json.loads((d / "FROZEN.json").read_text())["files"]
    assert "run-protocol.md is not frozen" not in instruments.verify(d, run=True)
    proto.write_text(proto.read_text().replace("5 times", "3 times"))
    assert "run-protocol.md changed after freezing" in instruments.verify(d)
    assert instruments.amend(d, "run-protocol", "fewer runs, for cost") == []
    assert instruments.verify(d) == []
