"""The TLA+ export of a declaration's model level (ADR-0043). TLC itself runs in the `tla` job;
these tests check what the exporter writes and what it leaves out."""
from pathlib import Path

import pytest
from test_decl import schema_doc_domain

from toprope.decl import Domain, load_domain
from toprope.harness.cli import main as harness_cli
from toprope.tla import Unsupported, export, value

ROOT = Path(__file__).resolve().parents[1]
PAID = ROOT / "examples/paid-media/paid-media.domain.yaml"


def test_values_are_tagged_so_tlc_never_compares_two_types():
    assert value(None) == "N" and value(True) == "B(TRUE)" and value(3) == "I(3)" and value(2.0) == "I(2)"
    assert value("draft") == 'S("draft")' and value(["a", 1]) == 'L(<<S("a"), I(1)>>)'
    assert value('say "hi"') == 'S("u:' + 'say "hi"'.encode().hex() + '")'     # quotes, non-ASCII: hex
    with pytest.raises(Unsupported):
        value(0.5)                                                         # TLC has no reals


def test_paid_media_is_modeled_whole():
    e = export(load_domain(PAID))
    assert e.left_out == {}
    assert sorted(e.steps) == ["Step_approve_budget_change_media_lead", "Step_grant_exception_media_lead",
                               "Step_propose_budget_change_analyst", "Step_reject_budget_change_media_lead"]
    for inv in load_domain(PAID).invariants:
        assert f"INVARIANT Inv_{inv.id.replace('-', '_')}" in e.cfg
    assert "CONSTRAINT Bound" in e.cfg and "CHECK_DEADLOCK FALSE" in e.cfg
    assert e.module.startswith("---- MODULE Toprope_paid_media ----") and e.module.rstrip().endswith("====")


def test_preconditions_actor_rules_and_effects_become_the_step():
    m = export(load_domain(PAID)).module
    approve = m[m.index("Step_approve_budget_change_media_lead =="):m.index("Step_grant_exception_media_lead ==")]
    assert '\\E mv \\in {<<"proposed", "none">>}' in approve                 # the matrix cell
    assert ('Pass(OpNe(Attr(R(o), "proposed_by"), Attr(Attr(Actor_media_lead, "principal"), "id")))'
            in approve)                                                    # not-the-proposer
    assert '("daily_budget" :> Attr(R(o), "proposed_budget"))' in approve   # a set effect, on the old state
    assert 'last\' = <<"approve_budget_change", "media_lead", i, <<>>>>' in approve
    propose = m[m.index("Step_propose_budget_change_analyst =="):m.index("Step_reject_budget_change_media_lead ==")]
    assert "OpLe(OpSub(p_daily_budget, Attr(R(o), \"daily_budget\")), I(500))" in propose   # step-limit, over params
    assert "p_daily_budget \\in {I(0), I(1)" in propose


def test_what_the_model_cannot_hold_is_left_out_and_named():
    e = export(Domain.model_validate(schema_doc_domain()))
    assert e.left_out == {"approve_experiment": "it uses the link path target.guardrails",
                          "launch_experiment": "it uses the function now()"}
    assert "Next == FALSE" in e.module                                   # nothing modeled: nothing to step


def test_self_domains_leave_out_only_what_creates_objects_or_follows_links():
    for f in ("domains/authoring/authoring.domain.yaml", "domains/delivery/delivery.domain.yaml"):
        e = export(load_domain(ROOT / f))
        assert all(v == "it creates an object" or "link path" in v for v in e.left_out.values()), e.left_out
        assert e.steps


def test_the_cli_writes_the_module_its_config_and_what_it_left_out(tmp_path, capsys):
    with pytest.raises(SystemExit) as ex:
        harness_cli(["--domain", str(PAID), "--tla", str(tmp_path)])
    assert ex.value.code == 0
    assert {p.name for p in tmp_path.iterdir()} == {"Toprope_paid_media.tla", "Toprope_paid_media.cfg",
                                                    "Toprope_paid_media.left-out.json"}
    assert "left out: nothing" in capsys.readouterr().out


def test_the_seeded_break_for_the_tla_job_is_paid_media_without_one_precondition():
    # The `tla` job requires TLC to find holdouts-never-change broken here (ADR-0043): a model
    # never seen failing proves nothing. Keep the fixture one change away from the example.
    import yaml
    seeded = yaml.safe_load((ROOT / "tests/tla/paid-media.no-holdout-guard.domain.yaml").read_text())
    example = yaml.safe_load(PAID.read_text())
    pre = example["actions"]["propose_budget_change"]["preconditions"]
    example["actions"]["propose_budget_change"]["preconditions"] = [p for p in pre if p["id"] != "not-a-holdout"]
    assert seeded == example
    workflow = (ROOT / ".github/workflows/tla.yml").read_text()
    assert "paid-media.no-holdout-guard.domain.yaml=breaks:Inv_holdouts_never_change" in workflow


def test_each_run_of_the_model_starts_from_one_fixture():
    # No modeled step or invariant reads another instance (link paths are left out), so checking
    # the fixtures one at a time reaches what checking them together would, in a sum, not a product.
    e = export(load_domain(PAID))
    init = e.module[e.module.index("Init =="):e.module.index("/\\ last = <<\"init\">>")]
    assert init.count("obj = (") == 2 and init.count("\\/ obj =") == 2      # C-search, C-holdout: each alone
    assert "\\E i \\in Ids_Campaign \\cap DOMAIN obj" in e.module
    assert "\\A i \\in Ids_Campaign \\cap DOMAIN obj" in e.module
