"""The impact of a change, stated as the decisions a person makes by approving it (ADR-0049, D2)."""
import copy
from pathlib import Path

from toprope.check import change_check
from toprope.check.decisions import decisions, render
from toprope.decl import Domain, load_domain

EX = Path(__file__).resolve().parents[1] / "examples"


def said(new_raw, old_raw):
    return [d["decide"] for d in decisions(Domain.model_validate(new_raw), Domain.model_validate(old_raw))]


def refunds():
    import yaml
    return yaml.safe_load((EX / "refunds/refunds.domain.yaml").read_text())


def test_a_changed_window_reads_as_the_rule_s_own_words():
    r = change_check(load_domain(EX / "refunds/refunds.30-days.domain.yaml"),
                     load_domain(EX / "refunds/refunds.domain.yaml"), examples=5)
    assert [d["decide"] for d in r.decisions] == [
        "refund_order: “Refunds are allowed within 7 days of purchase.” becomes "
        "“Refunds are allowed within 30 days of purchase.”"]
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
    assert "When an Order is refunded, refund_order is refused (“This order is already refunded.”); " \
           "it will be: moves it to paid" in out
    assert "refund_order: who may take it changes from support to support, finance (a person only)" in out
    assert "refund_order gets a new rule: “Only small orders are refunded here.”" in out


def test_a_removed_rule_says_what_will_no_longer_be_refused():
    old = refunds()
    new = copy.deepcopy(old)
    new["actions"]["refund_order"]["preconditions"] = []
    assert said(new, old) == ["refund_order loses the rule “Refunds are allowed within 7 days of purchase.”: "
                              "it will no longer refuse on it"]


def test_a_check_changed_under_the_same_reason_is_called_out():
    old = refunds()
    new = copy.deepcopy(old)
    new["actions"]["refund_order"]["preconditions"][0]["check"] = "true"
    (only,) = said(new, old)
    assert "now checks `true` (was `target.days_since_purchase <= 7`), and its reason still says the same" in only


def test_wording_and_examples_decide_nothing():
    old = refunds()
    new = copy.deepcopy(old)
    new["actions"]["refund_order"]["description"] = "Give the money back."
    new["objects"]["Order"]["description"] = "An order someone paid for."
    new["world"]["fixtures"].append({"Order": {"id": "O-1", "status": "paid", "days_since_purchase": 1}})
    assert said(new, old) == []
    assert render([]).startswith("Approving this decides nothing new")


def test_an_outcome_rule_and_a_first_version_are_named():
    old = refunds()
    new = copy.deepcopy(old)
    new["rules"] = {"only-people-refund": {"on": "Order.refunded", "requires": "human", "reason": "A person refunds."}}
    assert said(new, old) == ["Outcome rule new: “A person refunds.” (on Order.refunded)"]
    assert decisions(Domain.model_validate(old), None)[0]["decide"] == "refunds starts with 1 action(s) and 1 kind(s) of thing"


def test_the_review_a_person_confirms_from_ends_with_what_it_decides(tmp_path):
    from test_review_diff import workspace
    ws = workspace(tmp_path)
    c0 = ws.commit()["commit"]
    ws.approve_commit(c0, via="terminal", who="ana")
    ref = ws.chunks("docs")[0].ref
    ws.propose("actions.launch_experiment.actor", ["eng", "pm"], ref)
    text = ws.render_review()
    assert "Approving this decides:" in text and "launch_experiment: who may take it changes from eng to eng, pm" in text
