"""A template's rules change through named settings, with no YAML written by hand (ADR-0049)."""
import pytest

from toprope.adapters.cli.start import apply_settings, init, init_main, play, set_main, settings_of, templates
from toprope.decl import load_domain, validate_domain


@pytest.mark.parametrize("name", sorted(templates()))
def test_every_setting_names_a_precondition_and_its_default_is_the_template(tmp_path, name):
    out = init(f"my-{name}", name, tmp_path)
    before = (out / "domain.yaml").read_text()
    for key, spec in settings_of(out).items():
        apply_settings(out, [f"{key}={spec['default']}"])
    from toprope.decl import load_yaml
    raw, was = load_yaml((out / "domain.yaml").read_text()), load_yaml(before)
    assert raw == was                                   # the default writes the template's own rule
    assert play(out)[0]


def test_a_setting_changes_the_rule_and_its_reason_and_the_story_shows_it(tmp_path, capsys):
    out = init("shop", "refunds", tmp_path)
    set_main(["--dir", str(out), "window_days=30"])
    text = capsys.readouterr().out
    assert "window_days: 7 -> 30 (Refunds are allowed within 30 days of purchase.)" in text
    assert "changes 1 precondition(s)" in text
    assert "the story now ends differently: sam (support) asks to refund an order from day 8 -> ok" in text
    pre = load_domain(out / "domain.yaml").actions["refund_order"].preconditions[0]
    assert pre.check == "target.days_since_purchase <= 30"
    set_main(["--dir", str(out), "--list"])
    assert "window_days = 30" in capsys.readouterr().out


def test_init_can_set_a_value_from_the_start(tmp_path, capsys):
    init_main(["acc", "--template", "approval", "--dir", str(tmp_path), "--set", "prod_approver=manager"])
    d = load_domain(tmp_path / "acc" / "domain.yaml")
    assert not [i for i in validate_domain(d) if i.severity == "error"]
    assert "'manager' in actor.roles" in d.actions["approve_request"].preconditions[1].check


@pytest.mark.parametrize("arg, says", [
    ("window_days=abc", "is a whole number"),
    ("window_days=-3", "must be positive"),
    ("nope=1", "no setting 'nope'. Fix: use one of window_days"),
    ("window_days", "is not name=value"),
])
def test_a_wrong_value_is_refused_with_its_fix_and_nothing_is_written(tmp_path, arg, says):
    out = init("shop", "refunds", tmp_path)
    before = (out / "domain.yaml").read_text()
    with pytest.raises(SystemExit, match=says):
        set_main(["--dir", str(out), arg])
    assert (out / "domain.yaml").read_text() == before


def test_a_role_setting_takes_only_a_declared_role(tmp_path):
    with pytest.raises(SystemExit, match="'ceo' is not a role of this domain. Fix: use one of member, manager, security"):
        init_main(["acc", "--template", "approval", "--dir", str(tmp_path), "--set", "prod_approver=ceo"])
    assert not (tmp_path / "acc").exists()
