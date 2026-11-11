"""The story and the domain's store keep in step with domain.yaml after a change (ADR-0053, F2)."""
import json

import pytest
import yaml

from toprope.adapters.cli import main as run
from toprope.adapters.cli.rule import add_main
from toprope.adapters.cli.start import init, init_main, play, set_main, try_main


def test_accept_makes_the_story_expect_what_happens_now_and_shows_the_change(tmp_path, capsys):
    out = init("shop", "refunds", tmp_path)
    set_main(["--dir", str(out), "window_days=30"])
    said = capsys.readouterr().out
    assert "if that is what you meant, record it in the story:" in said and "toprope-try --accept" in said
    with pytest.raises(SystemExit, match="Fix: if you changed domain.yaml on purpose, run `toprope-try --accept`"):
        try_main(["--dir", str(out)])
    capsys.readouterr()
    try_main(["--dir", str(out), "--accept"])
    said = capsys.readouterr().out
    assert "step 1: sam (support) asks to refund an order from day 8: denied (within-window) -> ok" in said
    try_main(["--dir", str(out)])                       # exits 0 now
    step = yaml.safe_load((out / "story.yaml").read_text())["steps"][1]
    assert step["expect"] == "ok" and "code" not in step


def test_accept_does_not_record_a_step_that_cannot_run(tmp_path):
    out = init("shop", "refunds", tmp_path)
    decl = out / "domain.yaml"
    decl.write_text(decl.read_text().replace("id: O-8,", "id: O-9,"))
    before = (out / "story.yaml").read_text()
    with pytest.raises(SystemExit, match=r"these steps cannot run on domain.yaml as it is: step 1 \(refund_order O-8\): "
                                         r"No Order O-8. Fix: .*undo the hand edit"):
        try_main(["--dir", str(out), "--accept"])
    assert (out / "story.yaml").read_text() == before


def store_ids(out):
    from toprope.store import open_store
    s = open_store(f"sqlite:{out / '.toprope/events.db'}")
    try:
        return {sid: s.read(sid)[0].payload["changes"] for sid in s.streams()}
    finally:
        s.close()


def test_a_command_that_changes_the_examples_reseeds_an_unused_store(tmp_path, capsys):
    out = init("acc", "approval", tmp_path)
    add_main(["--dir", str(out), "field", "amount", "--set-by", "submit_request", "--default", "0"])
    assert "the domain's store now holds the new examples" in capsys.readouterr().out
    assert store_ids(out)["R-wiki"]["amount"] == 0


def test_a_used_store_is_never_reset_silently_and_reset_keeps_the_old_file(tmp_path, monkeypatch, capsys):
    out = init("acc", "approval", tmp_path)
    monkeypatch.chdir(out)
    run(["submit_request", "R-wiki", "--token", "t-mia"])
    add_main(["--dir", str(out), "field", "amount", "--set-by", "submit_request", "--default", "0"])
    said = capsys.readouterr().out
    assert "the domain's store was seeded before this change" in said and "toprope-try --reset" in said
    assert "amount" not in store_ids(out)["R-wiki"]           # what the person did is still there
    with pytest.raises(SystemExit):
        run(["approve_request", "R-nope", "--token", "t-sec"])
    denied = json.loads(capsys.readouterr().out)
    assert denied["code"] == "not-found" and "toprope-try --reset" in denied["fix"]
    try_main(["--reset"])
    assert "now holds the examples of domain.yaml; what was there before is kept in events-" in capsys.readouterr().out
    assert store_ids(out)["R-wiki"]["amount"] == 0
    assert len(list((out / ".toprope").glob("events-*.db"))) == 1


def test_run_reseeds_an_unused_store_after_a_hand_edit(tmp_path, monkeypatch, capsys):
    out = init("shop", "refunds", tmp_path)
    decl = out / "domain.yaml"
    decl.write_text(decl.read_text().replace("- Order: {id: O-8,", "- Order: {id: O-20, status: paid, "
                                             "days_since_purchase: 20}\n    - Order: {id: O-8,"))
    monkeypatch.chdir(out)
    with pytest.raises(SystemExit):
        run(["refund_order", "O-20", "--token", "t-sam"])        # found: the store was seeded again
    assert json.loads(capsys.readouterr().out)["code"] == "within-window"


def test_a_refusal_the_store_causes_names_its_fix(tmp_path, monkeypatch, capsys):
    out = init("shop", "refunds", tmp_path)
    monkeypatch.chdir(out)
    with pytest.raises(SystemExit):
        run(["refund_order", "O-77", "--token", "t-sam"])
    out_ = json.loads(capsys.readouterr().out)
    assert out_["code"] == "not-found" and out_["fix"].startswith("use the id of a Order the store has (O-3, O-8")


def test_init_prints_the_next_command_as_it_can_be_typed(tmp_path, capsys):
    init_main(["acc", "--template", "approval", "--dir", str(tmp_path)])
    text = capsys.readouterr().out
    assert "\n  uv run --project " in text and text.rstrip().endswith("toprope-try")


def test_the_story_reads_as_plain_words(tmp_path):
    from toprope.adapters.cli.start import templates
    for name in templates():
        ok, rows = play(init(f"my-{name}", name, tmp_path / name))
        assert not [r["asks"] for r in rows if r["asks"].startswith("ask ")], name   # never "asks to ask …"
