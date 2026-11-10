"""An extractor plugged in from outside (ADR-0051): the Ossie example package, found through the
entry point its own pyproject declares, reads an Ossie ontology into a proposed draft."""
import importlib.metadata as md
import sys
import tomllib
from pathlib import Path

import pytest

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
