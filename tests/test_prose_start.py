"""Start a domain from a sentence: the closest template, the rules it recognises as commands,
the rest as questions; a draft the person checks (ADR-0053, decided 1)."""
import re

import pytest

from toprope.adapters.cli.prose import choose_template
from toprope.adapters.cli.start import init_main, play
from toprope.decl import load_domain

SENTENCE = ("Staff submit purchase orders; a lead approves or rejects them. An order over 5,000 needs a director. "
            "Nobody approves an order they submitted. Orders are approved within 14 days. We like coffee.")


@pytest.mark.parametrize("text, template", [
    ("Support refunds an order a customer paid for", "refunds"),
    ("Engineers ship a release once its tests pass", "release"),
    ("An analyst decides whether an experiment's variant ships", "experiment"),
    ("Analysts propose a daily budget for each ad campaign", "budget"),
    ("Something happens to things", "approval"),                    # nothing matches: the most general
])
def test_the_closest_template_is_the_one_whose_words_it_uses(text, template):
    assert choose_template(text)[0] == template


def test_a_sentence_becomes_a_working_draft_with_its_rules_proposed(tmp_path, capsys):
    init_main([SENTENCE, "--dir", str(tmp_path)])
    said = capsys.readouterr().out
    out = tmp_path / "my-purchase-orders"
    d = load_domain(out / "domain.yaml")
    assert set(d.objects) == {"PurchaseOrder"} and "approve_purchase_order" in d.actions
    pres = {p.id: p for p in d.actions["approve_purchase_order"].preconditions}
    assert pres["amount-over-5000-needs-director"].check == \
        "not (target.amount > 5000) or 'director' in actor.roles"
    assert pres["amount-over-5000-needs-director"].status.value == "proposed"
    assert pres["amount-over-5000-needs-director"].source.quote == "An order over 5,000 needs a director."
    assert pres["within-14-days"].status.value == "proposed"
    assert pres["not-the-requester"].status is None                # the template had it: no proposal made
    assert "your sentence says what the template already has:\n  not-the-requester" in said
    assert "kept from the template, not from your sentence" in said and "prod-needs-security" in said
    assert 'who is "staff"?' in said and "toprope-add role staff --may submit_purchase_order" in said
    assert 'who is "lead"?' in said
    assert 'I did not understand "We like coffee."' in said
    assert "This is a draft" in said and "toprope-rule confirm" in said
    ok, rows = play(out)                                            # toprope-try shows it, and passes
    assert ok and any(r["code"] == "amount-over-5000-needs-director" for r in rows)


def test_the_same_sentence_gives_the_same_draft(tmp_path, capsys):
    init_main([SENTENCE, "--dir", str(tmp_path / "a")])
    init_main([SENTENCE, "--dir", str(tmp_path / "b")])
    capsys.readouterr()
    for f in ("domain.yaml", "story.yaml"):
        a = (tmp_path / "a/my-purchase-orders" / f).read_text()
        b = (tmp_path / "b/my-purchase-orders" / f).read_text()
        when = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00")          # the window's example: today - 15 days
        assert when.sub("T", a) == when.sub("T", b)


def test_person_only_and_a_named_template_and_name(tmp_path, capsys):
    init_main(["Support refunds an order; agents cannot refund, only a person may.", "--name", "shop",
               "--dir", str(tmp_path)])
    capsys.readouterr()
    d = load_domain(tmp_path / "shop" / "domain.yaml")
    assert d.actions["refund_order"].requires == "human" and d.actions["refund_order"].status.value == "proposed"
    assert play(tmp_path / "shop")[0]


def test_a_rule_it_reads_but_cannot_place_is_asked_not_guessed(tmp_path, capsys):
    init_main(["Analysts propose a daily budget for a campaign. A change over 900 needs a media_lead.",
               "--dir", str(tmp_path), "--name", "ads"])
    said = capsys.readouterr().out
    assert "which number is it about (daily_budget, proposed_budget)?" in said
    assert "toprope-rule threshold --action approve_budget_change" in said


def test_a_bad_name_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(SystemExit, match="'Ads Team' is not a domain name. Fix: give --name"):
        init_main([SENTENCE, "--name", "Ads Team", "--dir", str(tmp_path)])
    assert not list(tmp_path.iterdir())
