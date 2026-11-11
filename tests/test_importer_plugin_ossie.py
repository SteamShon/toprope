"""An extractor plugged in from outside (ADR-0051): the Ossie example package, found through the
entry point its own pyproject declares, reads an Ossie ontology into a proposed draft."""
import importlib.metadata as md
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from toprope.decl import Domain, validate_domain
from toprope.decl.provenance import proposed_elements
from toprope.importers import Profile, import_source, port

PKG = Path(__file__).resolve().parents[1] / "examples/plugins/toprope-ossie"
SHOP, FLIGHTS = str(PKG / "examples/orders.ossie.yaml"), str(PKG / "examples/flights.ontology.yaml")


@pytest.fixture(autouse=True)
def installed(monkeypatch):
    """What `pip install examples/plugins/toprope-ossie` gives: its src on the path and its entry points."""
    meta = tomllib.loads((PKG / "pyproject.toml").read_text())
    eps = [md.EntryPoint(name, value, group) for group, names in meta["project"]["entry-points"].items()
           for name, value in names.items()]
    monkeypatch.syspath_prepend(str(PKG / "src"))
    monkeypatch.setattr(md, "entry_points", lambda group: [e for e in eps if e.group == group])
    monkeypatch.setattr(port, "_discovered", False)
    monkeypatch.setattr(port, "_EXTRACTORS", {})
    monkeypatch.setattr(port, "_READERS", {})
    yield
    sys.modules.pop("toprope_ossie", None)


def valid(draft):
    d = Domain.model_validate(draft)
    assert not [i for i in validate_domain(d) if i.severity == "error"]
    return d


def test_an_ossie_ontology_becomes_things_facts_links_and_stages():
    out = import_source("ossie", SHOP, domain="shop")
    d = valid(out["draft"])
    assert set(d.objects) == {"Customer", "Order"}
    order = d.objects["Order"].properties
    assert order["status"].enum == ["paid", "shipped", "refunded"] and not order["status"].optional  # requires
    assert order["total"].type == "number" and order["total"].min == 0 and order["total"].optional
    assert order["placed_at"].type == "datetime" and order["gift"].type == "boolean"
    assert not order["id"].optional                                       # it identifies an Order
    link = d.links["order_customer"]
    assert (link.from_, link.to, link.cardinality, link.required) == ("Order", "Customer", "many-to-one", True)
    assert d.transitions["Order"].field == "status" and set(d.transitions["Order"].matrix) == {"paid", "shipped", "refunded"}
    assert d.objects["Order"].source.ref == f"{SHOP}#/ontology/3"
    assert "What happens to Customer, Order, and who may do it? (Ossie describes things, not actions)" in out["questions"]
    assert any("COUNT[Order] >= 0" in q for q in out["questions"])
    assert set(proposed_elements(out["draft"])) >= {"objects.Order", "objects.Customer", "links.order_customer"}


def test_the_official_ossie_example_reads_and_says_what_it_cannot_translate():
    out = import_source("ossie", FLIGHTS, domain="flights")
    d = valid(out["draft"])
    assert len(d.objects) == 12                                           # every EntityType, no ValueType
    assert d.objects["CancelationReason"].properties["code"].enum == ["A", "B", "C", "D"]
    assert d.objects["Airport"].properties["latitude"].min == -90 and not d.objects["Airport"].properties["latitude"].optional
    assert d.objects["Flight"].properties["canceled"].type == "boolean"
    assert d.links["city_state"].to == "State"
    assert "average_departure_delay" not in d.objects["Route"].properties   # derived: asked, not kept
    q = "\n".join(out["questions"])
    assert "Route.average_departure_delay is derived" in q
    assert "Flight.registers_latitude_series relates Flight to DateTime, DegreesLatitude" in q
    assert "`Flight.scheduled_departure < Flight.scheduled_arrival`" in q


def test_a_profile_renames_and_ignores_ossie_concepts():
    d = valid(import_source("ossie", SHOP, domain="shop",
                            profile=Profile(rename={"Order": "Purchase"}, ignore=["Customer"]))["draft"])
    assert set(d.objects) == {"Purchase"} and "customer" not in d.objects["Purchase"].properties
    assert not d.links


def test_a_semantic_model_without_an_ontology_names_the_document_to_export(tmp_path):
    f = tmp_path / "model.yaml"
    f.write_text("version: 0.3.0.dev0\nname: m\ndatasets: []\n")
    with pytest.raises(SystemExit, match="no `ontology` list. Fix: give the Ossie ontology document"):
        import_source("ossie", str(f))


# Review of #226 (2026-11-10): each case below gave a silently wrong draft or a traceback.

def _read(tmp_path, ontology, profile=None):
    f = tmp_path / "o.yaml"
    f.write_text(yaml.safe_dump({"version": "0.3.0.dev0", "name": "t", "ontology": ontology}))
    return import_source("ossie", str(f), profile=profile)


def rel(name, concept=None, mult="ManyToOne", **kw):
    return {"name": name, "roles": [{"concept": concept}] if concept else [], "verbalizes": ["x"],
            **({"multiplicity": mult} if mult else {}), **kw}


def test_limits_on_a_value_type_and_its_supertypes_all_hold(tmp_path):
    out = _read(tmp_path, [
        {"concept": "S", "type": "ValueType", "extends": ["String"], "requires": ["S == 'a' OR S == 'b' OR S == 'a'"]},
        {"concept": "T", "type": "ValueType", "extends": ["S"], "requires": ["T == 'a'"]},
        {"concept": "N", "type": "ValueType", "extends": ["Integer"], "requires": ["N >= 0", "N <= 100"]},
        {"concept": "M", "type": "ValueType", "extends": ["N"], "requires": ["M >= 10"]},
        {"concept": "Box", "type": "EntityType", "relationships": [rel("t", "T"), rel("s", "S"), rel("m", "M")]}])
    p = valid(out["draft"]).objects["Box"].properties
    assert p["t"].enum == ["a"] and p["s"].enum == ["a", "b"]
    assert (p["m"].min, p["m"].max) == (10, 100)


def test_names_that_collide_are_conflicts_and_nothing_is_dropped_silently(tmp_path):
    out = _read(tmp_path, [
        {"concept": "Order", "type": "EntityType", "requires": ["Order.nope"],
         "relationships": [rel("placedAt", "DateTime"), rel("placed_at", "Date"), rel("line_x", "Order"),
                           rel("owner", "Hidden"), rel("nicknames", "String", mult=None)]},
        {"concept": "OrderLine", "type": "EntityType", "relationships": [rel("x", "Order")]},
        {"concept": "order_line", "type": "EntityType"},
        {"concept": "Hidden", "type": "EntityType"},
        {"concept": "Staff", "type": "EntityType", "derived_by": ["EXISTS(Person.earns)"]}],
        profile=Profile(ignore=["Hidden"]))
    d = valid(out["draft"])
    conflicts, questions = "\n".join(out["conflicts"]), "\n".join(out["questions"])
    assert "Order.placed_at reads as `placed_at`, like another fact" in conflicts
    assert "links.order_line_x is said twice" in conflicts and "objects.OrderLine is said twice" in conflicts
    assert "has no relationship nope" in conflicts
    assert "links to Hidden, which the profile ignores" in questions
    assert "Can an Order have more than one nicknames?" in questions and "nicknames" not in d.objects["Order"].properties
    assert "Staff is derived" in questions and "Staff" not in d.objects
    assert "What happens to Order, OrderLine, and who" in questions


def test_a_stage_field_is_found_by_its_source_name(tmp_path):
    out = _read(tmp_path, [
        {"concept": "St", "type": "ValueType", "extends": ["String"], "requires": ["St == 'new' OR St == 'done'"]},
        {"concept": "Job", "type": "EntityType", "relationships": [rel("orderStatus", "St")]}],
        profile=Profile(stage_fields=["orderStatus"]))
    t = valid(out["draft"]).transitions["Job"]
    assert t.field == "order_status" and set(t.matrix) == {"new", "done"}


def test_a_role_that_is_not_a_mapping_is_refused_with_a_fix(tmp_path):
    with pytest.raises(SystemExit, match="is not `\\{concept: Name\\}`. Fix: write each role"):
        _read(tmp_path, [{"concept": "A", "type": "EntityType",
                          "relationships": [{"name": "b", "roles": ["String"], "verbalizes": ["x"]}]}])


def test_any_and_cycles_are_named_for_what_they_are(tmp_path):
    out = _read(tmp_path, [
        {"concept": "P", "type": "ValueType", "extends": ["Q"]}, {"concept": "Q", "type": "ValueType", "extends": ["P"]},
        {"concept": "A", "type": "EntityType", "relationships": [rel("p", "P"), rel("thing", "Any")]}])
    assert "in a cycle" in "\n".join(out["conflicts"])
    assert "links to Any, which names no thing" in "\n".join(out["questions"])
