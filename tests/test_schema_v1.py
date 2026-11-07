"""Every YAML example in docs/domain-schema.md must validate against the v1 JSON Schemas."""
import copy
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from toprope.decl import load_yaml

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = Draft202012Validator(json.loads((ROOT / "schema/domain.v1.schema.json").read_text()))
REPR = Draft202012Validator(json.loads((ROOT / "schema/representation.v1.schema.json").read_text()))
COMP = Draft202012Validator(json.loads((ROOT / "schema/composition.v1.schema.json").read_text()))
BLOCKS = [load_yaml(b) for b in re.findall(r"```yaml\n(.*?)```", (ROOT / "docs/domain-schema.md").read_text(), re.S)]


def merged(core: dict, fragment: dict) -> dict:
    out = copy.deepcopy(core)
    for k, v in fragment.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        elif isinstance(v, list) and isinstance(out.get(k), list):
            out[k] = out[k] + v
        else:
            out[k] = v
    return out


def errors(validator, doc):
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in validator.iter_errors(doc)]


@pytest.mark.parametrize("i", range(len(BLOCKS)))
def test_doc_example_validates(i):
    block, core = BLOCKS[i], BLOCKS[0]
    if "representation" in block or "overlay" in block:
        assert errors(REPR, block) == []
    elif "composition" in block:
        assert errors(COMP, block) == []
    elif "domain" in block:
        assert errors(DOMAIN, block) == []
    else:
        assert errors(DOMAIN, merged(core, block)) == []


def test_schema_rejects_typos_and_bad_cells():
    core = BLOCKS[0]
    bad = copy.deepcopy(core)
    bad["actions"]["approve_experiment"]["precondtions"] = []
    assert errors(DOMAIN, bad)
    bad = copy.deepcopy(core)
    bad["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = {"denny": "x"}
    assert errors(DOMAIN, bad)
    bad = merged(core, {"timers": {"t": {"on": "Experiment", "in_state": "running", "after": {}, "do": "x"}}})
    assert errors(DOMAIN, bad)


def test_every_construct_in_the_status_table_has_an_example():
    keys = set().union(*[b.keys() for b in BLOCKS]) | set(BLOCKS[0])
    for construct in ["purpose", "handoffs", "reservations", "timers", "functions", "external", "scenarios"]:
        assert construct in keys, construct


@pytest.mark.parametrize("fragment_key", ["reservations", "timers", "functions", "external"])
def test_kernel_refuses_defined_but_unimplemented_constructs(fragment_key):
    from pydantic import ValidationError
    from toprope.decl import Domain
    fragment = next(b for b in BLOCKS if fragment_key in b)
    with pytest.raises(ValidationError, match="not implemented until"):
        Domain.model_validate(merged(BLOCKS[0], {fragment_key: fragment[fragment_key]}))


def test_kernel_parses_the_handoffs_example():
    """Handoffs are implemented (M0a item 14). The doc's example names a sender action of the
    self domains, so on the experiment example it parses and the validator flags that action."""
    from toprope.decl import Domain, validate_domain
    fragment = next(b for b in BLOCKS if "handoffs" in b)
    d = Domain.model_validate(merged(BLOCKS[0], {"handoffs": fragment["handoffs"]}))
    h = d.handoffs["deliver_approved_version"]
    assert (h.to.domain, h.to.interface, h.to.action) == ("domain-delivery", "1.x", "request_delivery")
    assert ("unknown-action", "handoffs.deliver_approved_version.when") in {(i.code, i.where) for i in validate_domain(d)}


def test_kernel_refuses_cross_invariants_and_approvals_and_accepts_purpose():
    from pydantic import ValidationError
    from toprope.decl import Domain
    cross = next(b for b in BLOCKS if "reservations" in b)["invariants"]
    with pytest.raises(ValidationError, match="scope: cross"):
        Domain.model_validate(merged(BLOCKS[0], {"invariants": cross}))
    approvals = next(b for b in BLOCKS if "actions" in b and "ship_experiment" in b["actions"])
    with pytest.raises(ValidationError, match="approvals"):
        Domain.model_validate(merged(BLOCKS[0], approvals))
    purpose = next(b for b in BLOCKS if "purpose" in b)
    assert Domain.model_validate(merged(BLOCKS[0], purpose)).purpose.success_metric.direction == "up"


# -- the published schema and the kernel must agree (beyond documented not-yet constructs) -------
def _kernel_accepts(doc) -> bool:
    from pydantic import ValidationError
    from toprope.decl import Domain, validate_domain
    try:
        d = Domain.model_validate(doc)
    except ValidationError:
        return False
    return not [i for i in validate_domain(d) if i.severity == "error"]


def _probe(mutate):
    doc = copy.deepcopy(BLOCKS[0])
    mutate(doc)
    return doc


PROBES = {
    "empty actor list": lambda d: d["actions"]["approve_experiment"].__setitem__("actor", []),
    "version 0": lambda d: d.__setitem__("version", 0),
    "list value in set": lambda d: d["actions"]["approve_experiment"]["effects"][0]["set"].__setitem__("x", [1]),
    "bad id": lambda d: d.__setitem__("domain", "has space"),
    "step without actor": lambda d: d.setdefault("scenarios", []).append(
        {"id": "s", "steps": [{"actor": {}, "do": "approve_experiment", "target": "E-onboarding"}]}),
    "create effect": lambda d: d["actions"]["approve_experiment"]["effects"].append({"create": "Readout"}),
    "enforced_by on aggregate": lambda d: d["invariants"][0].__setitem__("enforced_by", "slot"),
}


@pytest.mark.parametrize("name", PROBES)
def test_schema_and_kernel_agree(name):
    doc = _probe(PROBES[name])
    assert bool(errors(DOMAIN, doc)) and not _kernel_accepts(doc), name


def test_system_is_a_reserved_actor():
    doc = _probe(lambda d: d["actions"]["launch_experiment"].__setitem__("actor", ["eng", "system"]))
    assert not errors(DOMAIN, doc) and _kernel_accepts(doc)


def test_external_actors_refused_until_m0b():
    from pydantic import ValidationError
    from toprope.decl import Domain
    doc = _probe(lambda d: d["actions"]["launch_experiment"].__setitem__("actor", ["external:flags"]))
    with pytest.raises(ValidationError, match="external actors"):
        Domain.model_validate(doc)


def test_representation_view_kinds_are_closed():
    rep = copy.deepcopy(next(b for b in BLOCKS if "representation" in b))
    rep["views"]["Experiment"]["detial"] = {}
    assert errors(REPR, rep)


def test_composition_schema_and_kernel_agree():
    """The doc's composition example validates, and the kernel's model accepts it too."""
    from toprope.compose import CompositionSpec
    block = next(b for b in BLOCKS if "composition" in b)
    assert errors(COMP, block) == []
    spec = CompositionSpec.model_validate(block)
    assert [w.from_ for w in spec.wiring] == ["domain-authoring.deliver_approved_version"]
    bad = copy.deepcopy(block)
    bad["wiring"][0]["from"] = "no-dot"
    assert errors(COMP, bad)


# -- ADR-0042 §3: read visibility is defined now, built with the query tools (M0b) ----------------
def test_read_visibility_is_defined_in_the_schema_and_refused_by_the_kernel_until_m0b():
    from pydantic import ValidationError
    from toprope.decl import Domain
    fragment = next(b for b in BLOCKS if any("read" in (o or {}) for o in (b.get("objects") or {}).values()))
    doc = merged(BLOCKS[0], fragment)
    assert errors(DOMAIN, doc) == []                                     # the schema accepts it
    with pytest.raises(ValidationError, match="read visibility.*not implemented until M0b"):
        Domain.model_validate(doc)
    only_property = merged(BLOCKS[0], {"objects": {"Note": {"properties": {"text": {"type": "string", "read": ["pm"]}}}}})
    assert errors(DOMAIN, only_property) == []
    with pytest.raises(ValidationError, match="read visibility.*not implemented until M0b"):
        Domain.model_validate(only_property)
    bad = merged(BLOCKS[0], {"objects": {"Note": {"read": "pm", "properties": {}}}})
    assert errors(DOMAIN, bad)                                           # a list of roles, not a string
