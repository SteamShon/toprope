"""A proposed draft from a source a team already has, through ports (ADR-0049 A1, ADR-0051)."""
from pathlib import Path

import pytest
import yaml

from toprope.decl import Domain, validate_domain
from toprope.decl.provenance import proposed_elements
from toprope.importers import (
    Candidate,
    Extraction,
    Profile,
    Raw,
    import_source,
    kinds,
    register_extractor,
    register_reader,
)
from toprope.importers.cli import main

EX = Path(__file__).resolve().parents[1] / "examples/import"
API, SQL, WF = str(EX / "orders.openapi.yaml"), str(EX / "orders.sql"), str(EX / "support.workflow.json")


def valid(draft):
    d = Domain.model_validate(draft)
    assert not [i for i in validate_domain(d) if i.severity == "error"]
    return d


def test_openapi_schemas_become_things_and_changing_operations_become_actions():
    out = import_source("openapi", API, domain="shop")
    d = valid(out["draft"])
    assert list(d.objects) == ["Order"]                                 # NewOrder is only a request's shape
    assert d.objects["Order"].properties["status"].enum == ["paid", "shipped", "refunded"]
    assert d.objects["Order"].properties["placed_at"].type == "datetime"
    assert set(d.actions) == {"create_order", "refund_order"}            # a GET changes nothing
    assert d.actions["create_order"].creates == "Order" and d.actions["refund_order"].target == "Order"
    assert d.actions["refund_order"].params["reason"].type == "string" and d.actions["refund_order"].params["amount"].optional
    assert d.transitions["Order"].matrix["shipped"]["refund_order"] == "undecided"   # for the interview
    assert d.actions["refund_order"].source.ref == f"{API}#/paths/~1orders~1{{id}}~1refund/post"
    assert "Who may refund an order (refund_order)?" in out["questions"]


def test_sql_enum_types_and_checks_become_enum_facts_citing_their_line():
    d = valid(import_source("sql", SQL, domain="shop")["draft"])
    props = d.objects["Order"].properties
    assert props["status"].enum == ["paid", "shipped", "refunded"] and not props["status"].optional
    assert props["channel"].enum == ["web", "store"] and props["channel"].optional
    assert d.objects["Order"].source.ref == f"{SQL}#L3"


def test_a_workflow_export_becomes_stages_actions_and_cells_leaving_the_rest_open():
    d = valid(import_source("workflow", WF, domain="support")["draft"])
    m = d.transitions["Ticket"].matrix
    assert m["open"]["start_work"].to == "in_progress" and m["done"]["reopen"].to == "open"
    assert m["open"]["resolve"] == "undecided"                          # not in the export: asked, not assumed
    assert d.actions["resolve"].source.ref == f"{WF}#/transitions/1"


def test_everything_imported_is_proposed_until_a_person_confirms_it():
    draft = import_source("openapi", API, domain="shop")["draft"]
    assert set(proposed_elements(draft)) >= {"objects.Order", "actions.create_order", "actions.refund_order"}


def test_a_profile_changes_the_result_without_code(tmp_path):
    api = yaml.safe_load(Path(API).read_text())
    api["paths"]["/orders/{id}/refund"]["post"]["x-roles"] = ["support"]
    f = tmp_path / "api.yaml"
    f.write_text(yaml.safe_dump(api))
    prof = Profile(stage_fields=["phase"], roles_from="x-roles", rename={"refundOrder": "give_money_back"},
                   ignore=["createOrder"])
    d = valid(import_source("openapi", str(f), domain="shop", profile=prof)["draft"])
    assert set(d.actions) == {"give_money_back"} and d.actions["give_money_back"].actor == ["support"]
    assert "Order" not in d.transitions                                  # `status` is no stage for this team
    wf = valid(import_source("workflow", WF, domain="support", profile=Profile(object="Case"))["draft"])
    assert list(wf.objects) == ["Case"]


def test_a_profile_file_with_an_unknown_key_names_the_keys(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text("stage_feilds: [status]\n")
    with pytest.raises(SystemExit, match="unknown key\\(s\\) stage_feilds.*Fix: use .*stage_fields"):
        Profile.load(p)


def test_a_reader_and_an_extractor_plug_in_from_outside():
    class Memo:
        kind = "memo"

        def read(self, location, profile):
            return Raw(b"Thing: Gadget", f"memo:{location}")

    class Lines:
        kind = "lines"

        def extract(self, raw, profile):
            name = raw.data.decode().split(": ")[1]
            return Extraction([Candidate(f"objects.{name}", {"description": f"A {name}."}, raw.ref + "#1")],
                              ["Which facts does a Gadget have?"])
    register_reader(Memo())
    register_extractor(Lines())
    assert {"memo"} <= set(kinds()["readers"]) and {"lines"} <= set(kinds()["extractors"])
    out = import_source("lines", "note-7", domain="toys", via="memo")
    assert out["draft"]["objects"]["Gadget"]["source"] == {"kind": "system", "ref": "memo:note-7#1"}
    assert out["draft"]["objects"]["Gadget"]["status"] == "proposed"


def test_installed_packages_plug_in_through_entry_points(monkeypatch):
    import importlib.metadata as md

    from toprope.importers import port

    class EP:
        name, group = "jira", port.READERS_GROUP

        def load(self):
            class Jira:
                kind = "jira"

                def read(self, location, profile):
                    return Raw(b"{}", location)
            return Jira

    monkeypatch.setattr(port, "_discovered", False)
    monkeypatch.setattr(md, "entry_points", lambda group: [EP()] if group == port.READERS_GROUP else [])
    assert "jira" in kinds()["readers"]


def test_an_unknown_reader_or_extractor_names_the_installed_ones():
    with pytest.raises(SystemExit, match="no extractor 'csv'. Fix: use one of .*openapi.*or install a package"):
        import_source("csv", API)
    with pytest.raises(SystemExit, match="no reader 'ftp'. Fix: use one of .*file"):
        import_source("openapi", API, via="ftp")


def test_the_command_writes_the_draft_and_the_questions_and_never_overwrites(tmp_path, capsys):
    dest = tmp_path / "shop.domain.yaml"
    main(["openapi", API, "--domain", "shop", "--out", str(dest)])
    text = capsys.readouterr().out
    assert "1 thing(s), 2 action(s), 1 with stages; every element is proposed" in text
    assert "what the source cannot say:" in text and valid(yaml.safe_load(dest.read_text()))
    with pytest.raises(SystemExit, match="exists. Fix: give --out a new file"):
        main(["openapi", API, "--out", str(dest)])
    main(["--list"])
    assert "extractors: " in capsys.readouterr().out


def test_a_source_with_nothing_to_import_says_what_was_looked_for(tmp_path):
    f = tmp_path / "empty.sql"
    f.write_text("SELECT 1;")
    with pytest.raises(SystemExit, match="nothing to import.*Fix: check that it is sql"):
        main(["sql", str(f), "--out", str(tmp_path / "x.yaml")])


def test_the_built_ins_come_back_when_the_registry_starts_over(monkeypatch):
    from toprope.importers import port
    kinds()                                                                # the built-in modules are imported
    monkeypatch.setattr(port, "_discovered", False)
    monkeypatch.setattr(port, "_READERS", {})
    monkeypatch.setattr(port, "_EXTRACTORS", {})
    assert {"file", "http"} <= set(kinds()["readers"]) and {"openapi", "sql", "workflow"} <= set(kinds()["extractors"])
