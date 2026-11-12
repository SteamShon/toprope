"""experiments/tools/m2_heldout.py: M2's held-out items are checked and sealed without showing
their content. The items here are format filler, not gold."""
import argparse
import csv
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


# --- `ask`: fixed questions at a terminal (requested 2026-11-12); answers are format filler ---

def _script(answers):
    it = iter(answers)
    return lambda prompt: next(it)


def _ask(tmp_path, answers, notes=None, terminal=True):
    out = []
    a = argparse.Namespace(file=str(tmp_path / "h.yaml"), from_notes=str(notes) if notes else None)
    ho.cmd_ask(a, ask=_script(answers), say=out.append, terminal=terminal)
    return yaml.safe_load((tmp_path / "h.yaml").read_text()), "\n".join(out)


def test_ask_turns_answers_into_items_that_validate(tmp_path, capsys):
    doc, shown = _ask(tmp_path, [
        "filler-domain",
        "rule one", "1", "a situation", "d", "a reason", "n", "", "y",       # outcome, tacit
        "rule two", "3", "an action", "role-a, role-b", "y", "x, y", "y",   # actors, written down
        "rule three", "2", "a question?", "y", "n", "", "n",                # yes_no, then stop
    ])
    assert "무엇에 대해 쓰나" in shown and "답은 어떤 형태로" in shown          # the guide comes first
    items = doc["items"]
    assert [i["id"] for i in items] == ["H01", "H02", "H03"]
    assert items[0]["answer"] == {"kind": "outcome", "expected": {"result": "denied", "reason": "a reason"}}
    assert items[0]["tacit"] is True and items[1]["tacit"] is False
    assert items[1]["answer"] == {"kind": "actors", "expected": ["role-a", "role-b"]}
    assert items[2]["answer"] == {"kind": "yes_no", "expected": "yes"}
    assert ho.problems(doc) == []
    ho.cmd_validate(argparse.Namespace(file=str(tmp_path / "h.yaml")))
    assert "3 items, 2 tacit" in capsys.readouterr().out


def test_ask_saves_each_item_so_a_stop_keeps_the_work(tmp_path):
    def answers():
        yield from ["d", "rule one", "4", "an event", "a state", "n", "", "y", "rule two"]
        raise KeyboardInterrupt
    gen = answers()
    out = []
    ho.cmd_ask(argparse.Namespace(file=str(tmp_path / "h.yaml"), from_notes=None),
               ask=lambda p: next(gen), say=out.append, terminal=True)
    doc = yaml.safe_load((tmp_path / "h.yaml").read_text())
    assert len(doc["items"]) == 1 and doc["items"][0]["answer"] == {"kind": "state", "expected": "a state"}
    assert any("이어서" in o for o in out)


def test_ask_from_notes_walks_the_memo_and_skips_rules_already_made(tmp_path):
    notes = tmp_path / "rules.txt"
    ho.cmd_notes(argparse.Namespace(file=str(notes)))
    assert "한 줄에 규칙 하나" in notes.read_text()
    notes.write_text(notes.read_text() + "rule one\n\nrule two\n")
    doc, _ = _ask(tmp_path, ["d", "2", "q1?", "n", "n", "", "s"], notes=notes)     # second rule skipped
    assert [i["rule"] for i in doc["items"]] == ["rule one"]
    doc, shown = _ask(tmp_path, ["2", "q2?", "y", "n", ""], notes=notes)           # resume: only rule two
    assert [i["rule"] for i in doc["items"]] == ["rule one", "rule two"] and "1개는 이미 항목" in shown


def test_ask_labels_a_rule_from_the_list_without_asking(tmp_path):
    # ADR-0056: a rule marked `[from-list ...]` in the memo came from an agent's list, so it is
    # written down somewhere (tacit: false) and tagged `from-list`; ask does not ask either.
    notes = tmp_path / "rules.txt"
    notes.write_text("[from-list L01] rule one\nrule two\n")
    doc, shown = _ask(tmp_path, ["d", "2", "q1?", "n",                   # listed: no tacit, no tag
                                 "2", "q2?", "y", "n", "own"], notes=notes)
    listed, own = doc["items"]
    assert listed["tacit"] is False and listed["covers"] == ["from-list"]
    assert own["tacit"] is True and own["covers"] == ["own"]
    assert "from-list" in shown and ho.problems(doc) == []


def test_ask_turns_a_csv_memo_into_items_without_questions(tmp_path):
    # Requested 2026-11-12: a memo as CSV (규칙, 상황, 결과, 이유, 출처), as a spreadsheet saves it.
    # A row with a situation is an item and nothing is asked; a row without one stays memo.
    notes = tmp_path / "rules.csv"
    notes.write_text("\ufeff규칙,상황,결과,이유,출처\n"
                     'rule one,"situation one, with a comma",거부,reason one,\n'
                     "rule two,situation two,허용,,from-list\n"
                     "rule three left as memo,,,,\n", encoding="utf-8")
    doc, shown = _ask(tmp_path, ["d"], notes=notes)                     # only the domain is asked
    own, listed = doc["items"]
    assert own["rule"] == "rule one" and own["tacit"] is True and own["covers"] == []
    assert own["answer"] == {"kind": "outcome", "expected": {"result": "denied", "reason": "reason one"}}
    assert "situation one, with a comma" in own["question"]
    assert listed["tacit"] is False and listed["covers"] == ["from-list"]
    assert listed["answer"] == {"kind": "outcome", "expected": {"result": "allowed"}}
    assert ho.problems(doc) == [] and "1줄은 상황이 없어" in shown
    doc, _ = _ask(tmp_path, [], notes=notes)                            # again: nothing new, nothing asked
    assert len(doc["items"]) == 2


def test_ask_refuses_a_csv_row_it_cannot_read_and_names_the_row(tmp_path):
    notes = tmp_path / "rules.csv"
    notes.write_text("규칙,상황,결과,이유,출처\nrule one,situation one,maybe,,\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="row 2"):
        _ask(tmp_path, ["d"], notes=notes)
    notes.write_text("rule,situation\nrule one,situation one\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="규칙,상황,결과,이유,출처"):
        _ask(tmp_path, ["d"], notes=notes)


def test_ask_csv_refuses_a_file_not_in_utf8_and_adds_a_repeated_rule_once(tmp_path):
    notes = tmp_path / "rules.csv"
    notes.write_bytes("규칙,상황,결과,이유,출처\nrule one,s,거부,,\n".encode("cp949"))
    with pytest.raises(SystemExit, match="UTF-8"):
        _ask(tmp_path, ["d"], notes=notes)
    notes.write_text("규칙,상황,결과,이유,출처\nrule one,s,거부,,\nrule one,s,거부,,\n", encoding="utf-8")
    doc, _ = _ask(tmp_path, ["d"], notes=notes)
    assert len(doc["items"]) == 1


def test_ask_csv_takes_blind_situations_judged_by_the_researcher(tmp_path):
    # ADR-0057: an agent that never saw the rules drafts situations (출처 blind-situation); the
    # researcher only judges each one. 모름 or an empty 결과 leaves the row out of the items.
    notes = tmp_path / "situations.csv"
    notes.write_text("규칙,상황,결과,이유,출처\n"
                     "S01,situation one,거부,,blind-situation\n"
                     "S02,situation two,모름,,blind-situation\n"
                     "S03,situation three,,,blind-situation\n", encoding="utf-8")
    doc, shown = _ask(tmp_path, ["d"], notes=notes)
    (item,) = doc["items"]
    assert item["rule"] == "S01" and item["covers"] == ["blind-situation"] and item["tacit"] is True
    assert item["answer"] == {"kind": "outcome", "expected": {"result": "denied"}}
    assert ho.problems(doc) == [] and "2줄은 판정이 없어" in shown


def test_csv_turns_a_text_memo_into_the_csv_to_fill(tmp_path, capsys):
    notes = tmp_path / "rules.txt"
    notes.write_text("# a comment\nrule one\n[from-list L01] rule, two\n\n")
    ho.cmd_csv(argparse.Namespace(file=str(notes)))
    out = tmp_path / "rules.csv"
    rows = list(csv.reader(out.open(encoding="utf-8-sig")))
    assert rows == [["규칙", "상황", "결과", "이유", "출처"],
                    ["rule one", "", "", "", ""], ["rule, two", "", "", "", "from-list"]]
    assert "2" in capsys.readouterr().out and "rule one" not in out.name
    with pytest.raises(SystemExit, match="exists"):
        ho.cmd_csv(argparse.Namespace(file=str(notes)))


def test_ask_runs_only_at_a_terminal_and_outside_the_repository(tmp_path):
    with pytest.raises(SystemExit, match="only at a terminal"):
        _ask(tmp_path, [], terminal=False)
    with pytest.raises(SystemExit, match="inside the repository"):
        ho.cmd_ask(argparse.Namespace(file=str(ROOT / "experiments/m2/h.yaml"), from_notes=None),
                   ask=_script([]), say=lambda s: None, terminal=True)
