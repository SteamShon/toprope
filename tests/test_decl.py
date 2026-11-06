import copy
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from toprope.decl import Domain, diff_interface, interface, load_yaml, validate_domain

ROOT = Path(__file__).resolve().parents[1]


def schema_doc_domain() -> dict:
    """The example in docs/domain-schema.md: first YAML block (domain) + the scenarios block."""
    blocks = re.findall(r"```yaml\n(.*?)```", (ROOT / "docs/domain-schema.md").read_text(), re.S)
    domain = load_yaml(blocks[0])
    scen = next(load_yaml(b) for b in blocks if b.lstrip().startswith("scenarios:"))
    domain["scenarios"] = scen["scenarios"]
    return domain


@pytest.fixture
def raw():
    return schema_doc_domain()


def errors(d: Domain):
    return [i for i in validate_domain(d) if i.severity == "error"]


def test_schema_doc_example_is_valid(raw):
    d = Domain.model_validate(raw)
    assert errors(d) == []
    assert set(d.transitions["Experiment"].matrix) == {"draft", "approved", "running", "ended", "decided"}


def test_unknown_keys_are_rejected(raw):
    raw["actions"]["approve_experiment"]["precondtions"] = []
    with pytest.raises(ValidationError):
        Domain.model_validate(raw)


@pytest.mark.parametrize("mutate, code", [
    (lambda r: r["transitions"]["Experiment"]["matrix"]["draft"].__setitem__("approve_experiment", "aproved"), "unknown-state"),
    (lambda r: r["transitions"]["Experiment"]["matrix"]["draft"].__setitem__("frobnicate", "approved"), "unknown-action"),
    (lambda r: r["actions"]["approve_experiment"].__setitem__("actor", ["admin"]), "unknown-role"),
    (lambda r: r["actions"]["approve_experiment"]["preconditions"][0].__setitem__("check", "count(target.guardrail) >= 1"), "unknown-path"),
    (lambda r: r["actions"]["approve_experiment"]["preconditions"][0].__setitem__("check", "count(target.guardrails >= 1"), "parse-error"),
    (lambda r: r["invariants"][0].__setitem__("check", "foo.bar == 1"), "unknown-root"),
    (lambda r: r["links"]["readout"].__setitem__("to", "Readouts"), "unknown-object"),
    (lambda r: r["world"]["fixtures"].append({"Experiment": {"id": "E-bare"}}), "duplicate-id"),
    (lambda r: r["scenarios"][0]["steps"][0].__setitem__("do", "approve"), "unknown-action"),
])
def test_structural_errors_are_reported(raw, mutate, code):
    mutate(raw)
    d = Domain.model_validate(raw)
    assert code in {i.code for i in errors(d)}


def test_paths_through_links_resolve(raw):
    raw["invariants"][0]["check"] = "count(target.guardrails) >= 0 and exists(target.hypothesis.statement)"
    assert errors(Domain.model_validate(raw)) == []
    raw["invariants"][0]["check"] = "exists(target.hypothesis.nope)"
    assert {i.code for i in errors(Domain.model_validate(raw))} == {"unknown-path"}


def test_missing_matrix_row_is_a_warning(raw):
    del raw["transitions"]["Experiment"]["matrix"]["decided"]
    issues = validate_domain(Domain.model_validate(raw))
    assert [i.code for i in issues if i.severity == "warning"] == ["missing-row"]


def test_interface_versioning(raw):
    old = interface(Domain.model_validate(raw))
    same = interface(Domain.model_validate(copy.deepcopy(raw)))
    assert diff_interface(old, same).bump == "none"

    text = copy.deepcopy(raw)
    text["actions"]["approve_experiment"]["description"] = "Sign off a drafted experiment."
    text["glossary"]["readout"] = "First look at the metrics."
    text["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = {"deny": "Approve it first."}
    d = diff_interface(old, interface(Domain.model_validate(text)))
    assert d.bump == "patch" and set(d.text_only) == {
        "action:approve_experiment", "term:readout", "cell:Experiment.draft.launch_experiment"}

    added = copy.deepcopy(raw)
    added["objects"]["Experiment"]["properties"]["tag"] = {"type": "string", "optional": True}
    assert diff_interface(old, interface(Domain.model_validate(added))).bump == "minor"

    removed = copy.deepcopy(raw)
    del removed["objects"]["Experiment"]["properties"]["started_at"]
    removed["actions"]["launch_experiment"]["effects"] = []
    removed["invariants"] = [i for i in removed["invariants"] if i["id"] != "running-has-start"]
    assert diff_interface(old, interface(Domain.model_validate(removed))).bump == "major"

    shape = copy.deepcopy(raw)
    shape["transitions"]["Experiment"]["matrix"]["ended"]["launch_experiment"] = "running"
    dd = diff_interface(old, interface(Domain.model_validate(shape)))
    assert dd.bump == "major" and dd.changed == ["cell:Experiment.ended.launch_experiment"]


def test_yaml12_booleans():
    assert load_yaml("on: Experiment\nyes: 1\nflag: true") == {"on": "Experiment", "yes": 1, "flag": True}


def test_yaml12_scalars_and_duplicate_keys():
    assert load_yaml("a: 12:30\nb: 0o17\nc: 0x1F") == {"a": "12:30", "b": 15, "c": 31}
    with pytest.raises(Exception):
        load_yaml("actions:\n  a: 1\n  a: 2\n")


def test_param_needs_exactly_one_kind(raw):
    raw["actions"]["approve_experiment"]["params"]["note"] = {}
    with pytest.raises(ValidationError):
        Domain.model_validate(raw)


def test_by_role_cells(raw):
    raw["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = {
        "by_role": {"approver": "approved", "pm": {"deny": "PMs request approval instead."}}}
    assert errors(Domain.model_validate(raw)) == []
    raw["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = {"by_role": {"ghost": "nowhere"}}
    assert {"unknown-role", "unknown-state"} <= {i.code for i in errors(Domain.model_validate(raw))}


def test_missing_cell_is_warned(raw):
    del raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"]
    warns = [i for i in validate_domain(Domain.model_validate(raw)) if i.code == "missing-cell"]
    assert len(warns) == 1 and "launch_experiment" in warns[0].message


def test_effect_values_are_checked_expressions(raw):
    raw["actions"]["launch_experiment"]["effects"] = [{"set": {"target.started_at": "nwo()"}}]
    assert errors(Domain.model_validate(raw)) == []  # unknown functions are runtime errors, not paths
    raw["actions"]["launch_experiment"]["effects"] = [{"set": {"target.started_at": "nwo"}}]
    assert {i.code for i in errors(Domain.model_validate(raw))} == {"unknown-root"}


def test_now_is_a_call_not_a_root(raw):
    raw["invariants"][1]["check"] = "target.started_at == now"
    assert "unknown-root" in {i.code for i in errors(Domain.model_validate(raw))}


def test_interface_bumps_follow_adr_0008(raw):
    raw["links"]["hypothesis"]["status"] = "proposed"       # an agent's proposal, confirmed below
    old = interface(Domain.model_validate(raw))
    ref = copy.deepcopy(raw)
    ref["actions"]["approve_experiment"]["params"]["note"] = {"ref": "Metric", "optional": True}
    assert diff_interface(old, interface(Domain.model_validate(ref))).bump == "major"
    conf = copy.deepcopy(raw)
    conf["links"]["hypothesis"]["status"] = "confirmed"
    assert diff_interface(old, interface(Domain.model_validate(conf))).bump == "patch"
    add = copy.deepcopy(raw)
    add["actions"]["approve_experiment"]["params"]["tag"] = {"type": "string", "optional": True}
    add["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "named", "check": "exists(target.name)", "reason": "Name it first."})
    d = diff_interface(old, interface(Domain.model_validate(add)))
    assert d.bump == "minor" and d.added == ["param:approve_experiment.tag", "precondition:approve_experiment.named"]


def test_unhashable_yaml_key_is_a_yaml_error():
    import yaml as _yaml
    with pytest.raises(_yaml.YAMLError):
        load_yaml("? [a, b]\n: 1\n")


def test_unsupported_effects_are_compile_errors(raw):
    raw["actions"]["approve_experiment"]["effects"].append({"create": "Readout"})
    raw["actions"]["launch_experiment"]["effects"].append({"set": {"new.name": "actor.id"}})
    assert [i.code for i in errors(Domain.model_validate(raw))] == ["unsupported-effect", "unsupported-effect"]


def test_an_object_s_own_id_is_a_known_path(raw):
    """`target.id` names the object itself (its stream id), e.g. to pass it to a kernel service."""
    raw["invariants"][0]["check"] = "exists(target.id) and exists(target.hypothesis.id)"
    assert errors(Domain.model_validate(raw)) == []
    raw["invariants"][0]["check"] = "exists(target.id.name)"
    assert {i.code for i in errors(Domain.model_validate(raw))} == {"unknown-path"}
