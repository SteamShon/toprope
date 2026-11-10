"""A person adds their own rule, role, person and field by command, with no YAML (ADR-0053, F2)."""
import pytest
import yaml

from toprope.adapters.cli.rule import add_main, rename_main, rule_main
from toprope.adapters.cli.start import init, play, try_main
from toprope.decl import load_domain, load_yaml


def files(out):
    return {f: (out / f).read_text() for f in ("domain.yaml", "tokens.yaml", "story.yaml")}


@pytest.fixture
def access(tmp_path):
    return init("acc", "approval", tmp_path)


def test_a_threshold_rule_is_enforced_and_the_story_shows_it_refusing(access, capsys):
    add_main(["--dir", str(access), "field", "amount", "--set-by", "submit_request", "--default", "0"])
    rule_main(["--dir", str(access), "threshold", "--action", "approve_request", "--when", "amount > 1,000",
               "--needs", "finance"])
    said = capsys.readouterr().out
    assert "added the role finance" in said and "finance may now take approve_request" in said
    d = load_domain(access / "domain.yaml")
    pre = d.actions["approve_request"].preconditions[-1]
    assert (pre.id, pre.check) == ("amount-over-1000-needs-finance",
                                   "not (target.amount > 1000) or 'finance' in actor.roles")
    assert pre.status is None                           # typed by the person: theirs, not a proposal
    ok, rows = play(access)
    assert ok
    shown = [r for r in rows if r["code"] == "amount-over-1000-needs-finance"]
    assert shown and shown[0]["reason"] == "When amount > 1000, only finance may approve request."
    assert rows[-1]["result"] == "ok" and "finance" in rows[-1]["who"]          # and finance gets through
    try_main(["--dir", str(access)])                                            # exits 0: the story ends as told
    assert "denied: When amount > 1000, only finance may approve request." in capsys.readouterr().out


def test_a_threshold_on_a_missing_field_names_the_command_that_adds_it(access):
    before = files(access)
    with pytest.raises(SystemExit, match=r"AccessRequest has no amount.*Fix: add it first: toprope-add field amount "
                                         r"--type integer --set-by submit_request"):
        rule_main(["--dir", str(access), "threshold", "--action", "approve_request", "--when", "amount > 10",
                   "--needs", "finance"])
    assert files(access) == before


def test_a_threshold_on_a_choice_field(access):
    rule_main(["--dir", str(access), "threshold", "--action", "approve_request", "--when", "system == crm",
               "--needs", "security", "--id", "crm-needs-security"])
    assert play(access)[0]
    with pytest.raises(SystemExit, match="system is one of wiki, crm, prod, not 'erp'. Fix:"):
        rule_main(["--dir", str(access), "threshold", "--action", "approve_request", "--when", "system == erp",
                   "--needs", "security"])


def test_no_self_approval_records_who_took_the_first_step_and_refuses_them(tmp_path):
    out = init("ab", "experiment", tmp_path)
    with pytest.raises(SystemExit, match="nothing records who made a Experiment theirs. Fix: give --by ACTION"):
        rule_main(["--dir", str(out), "no-self-approval", "--action", "start_experiment"])
    rule_main(["--dir", str(out), "no-self-approval", "--action", "start_experiment", "--by", "edit_experiment"])
    d = load_domain(out / "domain.yaml")
    assert "edit_experiment_by" in d.objects["Experiment"].properties
    assert d.actions["start_experiment"].preconditions[-1].check == "target.edit_experiment_by != actor.principal.id"
    ok, rows = play(out)
    assert ok is False                     # the agent edits, then starts, for the same engineer: now refused
    assert [r["code"] for r in rows if not r["as_told"]][0] == "not-who-edit-experiment"
    shown = rows[-2:]                      # and the story gained the steps that show the rule
    assert [r["result"] for r in shown] == ["ok", "denied"] and shown[-1]["code"] == "not-who-edit-experiment"


def test_a_rule_the_story_cannot_show_is_still_enforced_and_says_so(tmp_path, capsys):
    out = init("rel", "release", tmp_path)                  # nobody may both record tests and ship from one state
    rule_main(["--dir", str(out), "no-self-approval", "--action", "ship_release", "--by", "record_tests"])
    said = capsys.readouterr().out
    assert "the story could not show not-who-record-tests refusing with the examples there are (it is enforced" in said
    assert "the story now ends differently: the agent asks to ship 1.4.0 -> denied" in said


def test_no_self_approval_finds_the_rule_a_template_already_has(access, capsys):
    before = files(access)
    rule_main(["--dir", str(access), "no-self-approval", "--action", "approve_request"])
    assert "already a rule: not-the-requester" in capsys.readouterr().out
    assert load_yaml(files(access)["domain.yaml"]) == load_yaml(before["domain.yaml"])


def test_person_only_refuses_an_agent(tmp_path, capsys):
    out = init("shop", "refunds", tmp_path)
    rule_main(["--dir", str(out), "person-only", "--action", "refund_order"])
    assert "added an agent" in capsys.readouterr().out          # the template had none to show it with
    assert load_domain(out / "domain.yaml").actions["refund_order"].requires == "human"
    ok, rows = play(out)
    assert ok and rows[-1]["code"] == "actor" and rows[-1]["reason"] == "Only a person can refund_order."


def test_a_window_counts_days_from_an_action_or_a_field(access, tmp_path):
    rule_main(["--dir", str(access), "window", "--action", "approve_request", "--days", "30",
               "--since", "submit_request"])
    d = load_domain(access / "domain.yaml")
    assert d.actions["approve_request"].preconditions[-1].check == \
        "not exists(target.submit_request_at) or days_since(target.submit_request_at) <= 30"
    ok, rows = play(access)
    assert ok and rows[-1]["code"] == "within-30-days"
    shop = init("shop", "refunds", tmp_path / "b")
    rule_main(["--dir", str(shop), "window", "--action", "refund_order", "--days", "3", "--field",
               "days_since_purchase", "--id", "three-days"])
    assert play(shop)[0]
    with pytest.raises(SystemExit, match="a window counts days from something. Fix: give --field"):
        rule_main(["--dir", str(shop), "window", "--action", "refund_order", "--days", "3"])


def test_a_rule_is_listed_and_removed_with_its_story_steps(access, capsys):
    rule_main(["--dir", str(access), "person-only", "--action", "submit_request"])
    rule_main(["--dir", str(access), "list"])
    assert "person-only/submit_request  only a person may submit_request" in capsys.readouterr().out
    rule_main(["--dir", str(access), "remove", "prod-needs-security"])
    text = capsys.readouterr().out
    assert "the setting prod_approver went with it" in text and "removed 1 story step(s)" in text
    assert "prod-needs-security" not in (access / "domain.yaml").read_text()
    with pytest.raises(SystemExit, match="no rule 'nope'. Fix: see `toprope-rule list`"):
        rule_main(["--dir", str(access), "remove", "nope"])


def test_a_rule_command_that_would_break_the_declaration_writes_nothing(access):
    before = files(access)
    with pytest.raises(SystemExit, match="there is already a rule 'prod-needs-security'. Fix:"):
        rule_main(["--dir", str(access), "threshold", "--action", "approve_request", "--when", "system == prod",
                   "--needs", "security", "--id", "prod-needs-security"])
    with pytest.raises(SystemExit, match="no action 'approve'. Fix: use one of submit_request"):
        rule_main(["--dir", str(access), "person-only", "--action", "approve"])
    assert files(access) == before


def test_add_a_person_and_an_agent_to_tokens(access):
    with pytest.raises(SystemExit, match="no role finance. Fix: add it first: toprope-add role finance"):
        add_main(["--dir", str(access), "person", "fay", "--roles", "finance"])
    add_main(["--dir", str(access), "role", "finance", "--may", "approve_request"])
    add_main(["--dir", str(access), "person", "fay", "--roles", "finance"])
    add_main(["--dir", str(access), "agent", "helper", "--for", "fay", "--may", "approve_request"])
    tokens = load_yaml((access / "tokens.yaml").read_text())
    assert tokens["t-fay"] == {"id": "fay", "roles": ["finance"]}
    assert tokens["t-helper"]["on_behalf_of"] == {"id": "fay", "roles": ["finance"]}
    assert "finance" in load_domain(access / "domain.yaml").actions["approve_request"].actor
    with pytest.raises(SystemExit, match="fay is already in tokens.yaml. Fix:"):
        add_main(["--dir", str(access), "person", "fay", "--roles", "finance"])


def test_a_field_set_by_an_action_is_a_param_and_the_story_gives_it(access):
    add_main(["--dir", str(access), "field", "amount", "--set-by", "submit_request", "--default", "0"])
    d = load_domain(access / "domain.yaml")
    assert "amount" in d.actions["submit_request"].params
    assert all(fx["AccessRequest"]["amount"] == 0 for fx in d.world.fixtures)
    story = yaml.safe_load((access / "story.yaml").read_text())
    assert all(s["params"]["amount"] == 0 for s in story["steps"] if s["action"] == "submit_request")
    assert play(access)[0]


def test_rename_follows_a_name_everywhere(access):
    rename_main(["AccessRequest", "Claim", "--dir", str(access)])
    rename_main(["approve_request", "approve_claim", "--dir", str(access)])
    rename_main(["manager", "lead", "--dir", str(access)])
    rename_main(["requested_by", "submitted_by", "--dir", str(access)])
    d = load_domain(access / "domain.yaml")
    assert set(d.objects) == {"Claim"} and "approve_claim" in d.actions and "lead" in d.roles
    assert d.actions["approve_claim"].preconditions[0].check == "target.submitted_by != actor.principal.id"
    tokens = load_yaml((access / "tokens.yaml").read_text())
    assert tokens["t-max"]["roles"] == ["member", "lead"]
    story = yaml.safe_load((access / "story.yaml").read_text())
    assert story["settings"]["prod_approver"]["at"].startswith("actions.approve_claim.")
    assert "max (lead)" in {s["as"] for s in story["steps"]}
    assert play(access)[0]
    with pytest.raises(SystemExit, match="'claim' is not a name for a object. Fix: an object's name starts with a "
                                         "capital letter"):
        rename_main(["Claim", "claim", "--dir", str(access)])


def test_a_drafted_rule_is_proposed_until_the_person_confirms_it(access, capsys):
    from toprope.adapters.cli.rule import Draft, add_threshold
    draft = Draft.open(access)
    add_threshold(draft, "approve_request", "system == prod", "security", "prod-again", quote="prod is for security")
    draft.save()
    pre = load_domain(access / "domain.yaml").actions["approve_request"].preconditions[-1]
    assert (pre.status.value, pre.source.quote) == ("proposed", "prod is for security")
    rule_main(["--dir", str(access), "list"])
    assert "prod-again  (approve_request) When system == prod, only security may approve request.  [proposed]" \
        in capsys.readouterr().out
    with pytest.raises(SystemExit, match="not proposed: nope. Fix: confirm one of "
                                         "actions.approve_request.preconditions.prod-again"):
        rule_main(["--dir", str(access), "confirm", "nope"])
    rule_main(["--dir", str(access), "confirm", "prod-again"])
    assert "confirmed actions.approve_request.preconditions.prod-again" in capsys.readouterr().out
    assert load_domain(access / "domain.yaml").actions["approve_request"].preconditions[-1].status.value == "confirmed"


def test_renaming_a_recorded_field_renames_the_param_that_records_it(access):
    add_main(["--dir", str(access), "field", "amount", "--set-by", "submit_request", "--default", "0"])
    rename_main(["amount", "cost", "--dir", str(access)])
    d = load_domain(access / "domain.yaml")
    assert "cost" in d.actions["submit_request"].params and "amount" not in d.actions["submit_request"].params
    story = yaml.safe_load((access / "story.yaml").read_text())
    assert all(s["params"] == {"cost": 0} for s in story["steps"] if s["action"] == "submit_request")
    assert play(access)[0]
