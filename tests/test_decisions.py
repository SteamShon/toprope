"""The impact of a change, stated as the decisions a person makes by approving it (ADR-0049, D2)."""
import copy
from pathlib import Path

import yaml

from toprope.check import change_check
from toprope.check.decisions import decisions, render, unenforced
from toprope.decl import Domain, load_domain

EX = Path(__file__).resolve().parents[1] / "examples"
L, R = "“", "”"


def said(new_raw, old_raw):
    return [d["decide"] for d in decisions(Domain.model_validate(new_raw), Domain.model_validate(old_raw))]


def refunds():
    return yaml.safe_load((EX / "refunds/refunds.domain.yaml").read_text())


def test_a_changed_window_reads_as_the_rule_s_own_words_and_its_check():
    r = change_check(load_domain(EX / "refunds/refunds.30-days.domain.yaml"),
                     load_domain(EX / "refunds/refunds.domain.yaml"), examples=5)
    assert [d["decide"] for d in r.decisions] == [
        f"refund_order: {L}Refunds are allowed within 7 days of purchase.{R} becomes "
        f"{L}Refunds are allowed within 30 days of purchase.{R}",
        f"refund_order: the rule {L}Refunds are allowed within 30 days of purchase.{R} checks "
        "`target.days_since_purchase <= 30` (was `target.days_since_purchase <= 7`)"]
    assert r.to_json()["decisions"] == r.decisions


def test_cells_actors_the_person_floor_and_new_rules_each_say_what_changes():
    old = refunds()
    new = copy.deepcopy(old)
    new["transitions"]["Order"]["matrix"]["refunded"]["refund_order"] = "paid"
    new["actions"]["refund_order"]["actor"] = ["support", "finance"]
    new["actions"]["refund_order"]["requires"] = "human"
    new["actions"]["refund_order"]["preconditions"].append(
        {"id": "small", "check": "true", "reason": "Only small orders are refunded here."})
    out = said(new, old)
    assert (f"When an Order is refunded, refund_order is refused ({L}This order is already refunded.{R}); "
            "it will be: moves it to paid") in out
    assert "refund_order: who may take it changes from support to support, finance (a person only)" in out
    assert f"refund_order gets a new rule: {L}Only small orders are refunded here.{R} (checks `true`)" in out


def test_a_removed_rule_says_what_will_no_longer_be_refused():
    old = refunds()
    new = copy.deepcopy(old)
    new["actions"]["refund_order"]["preconditions"] = []
    assert said(new, old) == [f"refund_order loses the rule {L}Refunds are allowed within 7 days of purchase.{R}: "
                              "it will no longer refuse on it"]


def test_a_check_changed_under_the_same_reason_is_said():
    old = refunds()
    new = copy.deepcopy(old)
    new["actions"]["refund_order"]["preconditions"][0]["check"] = "true"
    assert said(new, old) == [f"refund_order: the rule {L}Refunds are allowed within 7 days of purchase.{R} "
                              "checks `true` (was `target.days_since_purchase <= 7`)"]


def test_a_check_and_its_reason_changing_together_are_both_said():
    old = refunds()
    new = copy.deepcopy(old)
    pre = new["actions"]["refund_order"]["preconditions"][0]
    pre["check"], pre["reason"] = "true", "Refunds are allowed within 30 days of purchase."
    out = said(new, old)
    assert len(out) == 2 and "checks `true` (was `target.days_since_purchase <= 7`)" in out[1]


def test_wording_and_examples_decide_nothing_and_are_counted():
    old = refunds()
    new = copy.deepcopy(old)
    new["actions"]["refund_order"]["description"] = "Give the money back."
    new["objects"]["Order"]["description"] = "An order someone paid for."
    new["world"]["fixtures"].append({"Order": {"id": "O-1", "status": "paid", "days_since_purchase": 1}})
    assert said(new, old) == []
    assert unenforced(Domain.model_validate(new), Domain.model_validate(old)) == 1      # the example
    assert render([], 1) == ("Approving this changes no rule: nothing it enforces is different.\n"
                             "Also changed, but enforced by nothing: 1 element(s) of the glossary, examples, "
                             "scenarios or purpose.\n")


def test_inputs_effects_stages_and_the_approval_rule_are_never_left_out():
    old = refunds()
    new = copy.deepcopy(old)
    new["actions"]["refund_order"]["params"] = {"amount": {"type": "integer"}}
    new["actions"]["refund_order"]["records_decision"] = True
    new["transitions"]["Order"]["initial"] = "paid"
    new["approval"] = {"distinct_from_author": True}
    out = said(new, old)
    assert any(s.startswith("refund_order takes a new input, amount") for s in out)
    assert any("its records decision changes from false to true" in s for s in out)
    assert any(s.startswith("Order's stages:") and '"initial": "paid"' in s for s in out)
    assert any(s.startswith("Who may approve a commit of this domain changes") for s in out)


def test_an_outcome_rule_is_named_with_who_it_requires_and_a_first_version_is_named():
    old = refunds()
    new = copy.deepcopy(old)
    new["rules"] = {"r": {"on": "Order.refunded", "requires": "human", "reason": "A person refunds."}}
    assert said(new, old) == [f"New outcome rule: {L}A person refunds.{R}: only a person may bring about Order.refunded"]
    newer = copy.deepcopy(new)
    newer["rules"]["r"]["requires"] = {"roles": ["finance"]}
    assert said(newer, new) == [f"Outcome rule {L}A person refunds.{R}: requires a person becomes role finance"]
    assert decisions(Domain.model_validate(old), None)[0]["decide"] == "refunds starts with 1 action(s) and 1 kind(s) of thing"


def test_a_removed_cell_says_what_it_did_before():
    old = refunds()
    new = copy.deepcopy(old)
    del new["transitions"]["Order"]["matrix"]["paid"]["refund_order"]
    assert said(new, old) == ["When an Order is paid, refund_order moves it to refunded; it will be undecided, so refused"]


def test_a_reason_cannot_add_a_line_to_the_list():
    old = refunds()
    new = copy.deepcopy(old)
    new["actions"]["refund_order"]["preconditions"][0]["reason"] = "Fine.\n  - Approving nothing"
    text = render(decisions(Domain.model_validate(new), Domain.model_validate(old)))
    assert text.count("\n  - ") == 1 and f"{L}Fine. - Approving nothing{R}" in text


def test_the_review_a_person_confirms_from_ends_with_what_it_decides(tmp_path):
    from test_review_diff import workspace
    ws = workspace(tmp_path)
    c0 = ws.commit()["commit"]
    ws.approve_commit(c0, via="terminal", who="ana")
    ws.propose("actions.launch_experiment.actor", ["eng", "pm"], ws.chunks("docs")[0].ref)
    text = ws.render_review()
    assert "Approving this decides:" in text and "launch_experiment: who may take it changes from eng to eng, pm" in text
