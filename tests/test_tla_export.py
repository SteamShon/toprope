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
    assert '("daily_budget" :> Store(Attr(R(o), "proposed_budget")))' in approve   # a set effect, on the old state
    assert 'last\' = <<"approve_budget_change", "media_lead", i, <<>>>>' in approve
    propose = m[m.index("Step_propose_budget_change_analyst =="):m.index("Step_reject_budget_change_media_lead ==")]
    assert "OpLe(OpSub(p_daily_budget, Attr(R(o), \"daily_budget\")), I(500))" in propose   # step-limit, over params
    assert "p_daily_budget \\in {I(0), I(1)" in propose


def test_what_the_model_cannot_hold_is_left_out_and_named():
    e = export(Domain.model_validate(schema_doc_domain()))
    assert e.left_out == {}                                              # links (#156) and time are modeled
    assert "Step_approve_experiment_approver" in e.steps                 # its link path (count of many)
    assert "Step_launch_experiment_eng" in e.steps                       # its `started_at: now()`
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "budget", "check": "target.planned_days + 1 > 0", "reason": "Planned."})
    raw["actions"]["approve_experiment"]["effects"].append({"set": {"target.note": "unknown_fn()"}})
    assert export(Domain.model_validate(raw)).left_out == {"approve_experiment": "it uses the function unknown_fn()"}


def test_self_domains_leave_nothing_out():
    for f in ("domains/authoring/authoring.domain.yaml", "domains/delivery/delivery.domain.yaml"):
        e = export(load_domain(ROOT / f))
        assert e.left_out == {}, e.left_out           # creation (#155) and link paths are modeled now
        assert e.steps


def test_a_link_reads_fixtures_and_only_what_no_action_changes():
    """A link path reads the linked fixtures from a constant. That is sound only for what no
    modeled action changes, so a field that changes stays left out, named."""
    e = export(load_domain(ROOT / "domains/authoring/authoring.domain.yaml"))
    assert 'Pass(OpExists(LinkOne(Fix_Source, Get(o, "origin"))))' in e.module      # elements-cite-a-source
    assert e.module.count("Fix_Source ==") == 1 and '"S-docs" :>' in e.module
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "metric-named", "check": "exists(target.primary_metric.name)", "reason": "A named metric."})
    ok = export(Domain.model_validate(raw))
    assert "approve_experiment" not in ok.left_out                        # Metric.name: no action sets it
    assert 'Attr(LinkOne(Fix_Metric, Get(o, "primary_metric")), "name")' in ok.module
    raw["actions"]["approve_experiment"]["preconditions"][-1]["check"] = "target.primary_metric.stage == 'x'"
    raw["objects"]["Metric"]["properties"]["stage"] = {"enum": ["x", "y"]}
    raw["actions"]["retire_metric"] = {"description": "Retire.", "actor": ["approver"], "target": "Metric",
                                       "effects": [{"set": {"target.stage": "'y'"}}]}
    bad = export(Domain.model_validate(raw))
    assert "a field that changes" in bad.left_out["approve_experiment"]


def test_creation_is_modeled_from_the_empty_world():
    """ADR-0043's follow-up: creating actions, left out before, are steps now. A creating step
    runs only from the empty world and makes one object, so a run still follows one object."""
    e = export(load_domain(ROOT / "domains/delivery/delivery.domain.yaml"))
    assert "Create_request_delivery_system" in e.steps                 # the `system` actor a handoff is
    assert 'Ids_DeliveryRequest == {"R1", "R2", "R3", "R4", "R5", "R6", "new-DeliveryRequest"}' in e.module
    init = e.module[e.module.index("Init =="):e.module.index('/\\ last = <<"init">>')]
    assert "obj = [x \\in {} |-> N]" in init                           # the empty world is a start
    create = e.module[e.module.index("Create_request_delivery_system =="):]
    create = create[:create.index("\n\n") if "\n\n" in create else len(create)]
    assert "DOMAIN obj = {}" in create and '("stage" :> S("requested"))' in create
    assert 'p_commit \\in {S("x")}' in create                       # nothing reads it: one value


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


def test_time_is_the_harness_clock_frozen():
    """`now()` is the harness's clock (replay uses the same); every ISO time the model can hold
    has its offset (`Secs`), and its whole days for `days_since` (`Days`); an effect stores
    `now()` as its ISO string, as the interpreter does."""
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "fresh", "check": "not exists(target.started_at) or days_since(target.started_at) < 30",
         "reason": "A recent start."})
    e = export(Domain.model_validate(raw))
    assert e.left_out == {}
    assert 'NowIso == "2026-01-01T00:00:00+00:00"' in e.module
    assert '("2025-11-02T00:00:00+00:00" :> 60)' in e.module             # Days: 60 days before the clock
    assert 'DaysSince(Attr(R(o), "started_at"))' in e.module
    assert '("started_at" :> Store(T(0)))' in e.module


def test_a_param_only_copied_into_a_field_nothing_reads_takes_one_value():
    """A string the declaration stores but never reads cannot change a step or a check; trying
    every candidate multiplied Authoring's states until TLC took hours (the M1 recheck)."""
    from toprope.tla import _unread_params
    raw = schema_doc_domain()
    raw["objects"]["Experiment"]["properties"]["memo"] = {"type": "string", "optional": True}
    raw["actions"]["approve_experiment"]["params"]["memo"] = {"type": "string"}
    raw["actions"]["approve_experiment"]["effects"].append({"set": {"target.memo": "params.memo"}})
    d = Domain.model_validate(raw)
    assert _unread_params(d, d.actions["approve_experiment"]) == {"memo"}
    step = export(d).module.split("Step_approve_experiment_approver ==")[1].split("\n\n")[0]
    assert step.count("p_memo \\in {") == 1 and step.split("p_memo \\in {")[1].split("}")[0].count(",") == 0
    raw["invariants"].append({"id": "memo-short", "on": "Experiment", "check": "count(target.memo) < 99",
                              "reason": "r"})
    read = Domain.model_validate(raw)
    assert _unread_params(read, read.actions["approve_experiment"]) == set()       # read: every value


def test_multiplication_is_modeled_as_tlc_multiplies_integers():
    """`*` (ADR-0058) becomes `OpMul`, an integer product in the model, so TLC checks a share rule."""
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "share", "check": "count(target.notes) * 100 <= 80 * 2", "reason": "A share."})
    e = export(Domain.model_validate(raw))
    assert e.left_out == {}
    assert "OpMul(a, b) == IF IsInt(a) /\\ IsInt(b) THEN I(a[2] * b[2]) ELSE E" in e.module
    assert "OpMul(OpCount(" in e.module
