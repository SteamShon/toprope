"""A proposed draft from a source a team already has, through ports (ADR-0049 A1, ADR-0051)."""
import json
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


# Review of #225 (2026-11-10): each case below gave an invalid draft, a lost element or a traceback.

def _src(tmp_path, name, text):
    f = tmp_path / name
    f.write_text(text)
    return str(f)


SHOP = """
openapi: 3.1.0
paths:
  /orders: {post: {operationId: createOrder}}
  /orders/{id}/refund: {post: {operationId: refundOrder}}
  /auth/login: {post: {operationId: login}}
components:
  schemas:
    Order:
      type: object
      required: [status]
      properties:
        status: {type: string, enum: [paid, shipped, null, paid]}
        note: {type: [string, "null"]}
        customer: {$ref: "#/components/schemas/Customer"}
    Customer: {type: object, properties: {email: {type: string}}}
"""


def test_an_operation_on_nothing_the_source_describes_is_asked_about_not_written_invalid(tmp_path):
    out = import_source("openapi", _src(tmp_path, "a.yaml", SHOP), domain="shop")
    d = valid(out["draft"])
    assert "login" not in d.actions and any("Which thing does login" in q for q in out["questions"])
    props = d.objects["Order"].properties
    assert props["status"].enum == ["paid", "shipped"] and props["status"].optional       # null: optional, once
    assert props["note"].type == "string" and props["note"].optional                      # 3.1 nullable
    assert d.links["order_customer"].to == "Customer"


def test_a_profile_renaming_or_ignoring_a_schema_keeps_the_actions_consistent(tmp_path):
    f = _src(tmp_path, "a.yaml", SHOP)
    d = valid(import_source("openapi", f, profile=Profile(rename={"Order": "Purchase"}))["draft"])
    assert d.actions["refund_order"].target == "Purchase" and d.actions["create_order"].creates == "Purchase"
    for ignore in (["Order"], ["Purchase"]):
        out = import_source("openapi", f, profile=Profile(rename={"Order": "Purchase"}, ignore=ignore))
        assert "Purchase" not in valid(out["draft"]).objects and "refund_order" not in out["draft"]["actions"]


def test_two_source_names_for_one_element_are_a_conflict_naming_both_places(tmp_path):
    f = _src(tmp_path, "a.yaml", """
paths:
  /orders: {delete: {}}
  /orders/{id}: {delete: {}}
components:
  schemas:
    Order: {type: object, properties: {status: {type: string, enum: [a, b]}, firstName: {type: string}, first-name: {type: integer}}}
    order: {type: object, properties: {total: {type: number}}}
""")
    out = import_source("openapi", f)
    d = valid(out["draft"])
    assert "status" in d.objects["Order"].properties and d.objects["Order"].properties["first_name"].type == "string"
    joined = "\n".join(out["conflicts"])
    assert "objects.Order is said twice" in joined and "actions.delete_orders is said twice" in joined
    assert "two facts read as `first_name`" in joined


def test_transitions_sharing_a_name_keep_every_move_and_an_unknown_target_is_asked(tmp_path):
    f = _src(tmp_path, "w.json", json.dumps({"statuses": ["Open", "In Progress", "Done"], "transitions": [
        {"name": "Close", "from": "Open", "to": "Done"}, {"name": "Close", "from": "In Progress", "to": "Done"},
        {"name": "Archive", "from": "Done", "to": "Archived"}]}))
    out = import_source("workflow", f)
    m = valid(out["draft"]).transitions["Ticket"].matrix
    assert m["open"]["close"].to == "done" and m["in_progress"]["close"].to == "done"
    assert any("'Archived', which is not among the statuses" in q for q in out["questions"])


def test_sql_reads_real_dialects_without_mixing_tables(tmp_path):
    f = _src(tmp_path, "s.sql", """
/* CREATE TABLE ghost (state text CHECK (state IN ('x'))); */
CREATE TABLE `orders` (
  status ENUM('paid','it''s','b,c') NOT NULL,
  id int
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
CREATE TYPE public.prio AS ENUM ('low', 'high');
CREATE TABLE public."Line Items" (prio public.prio);
create table statuses (state text check (state in ('on', 'off')));
""")
    d = valid(import_source("sql", f)["draft"])
    assert set(d.objects) == {"Order", "LineItem", "Status"}                          # no Ghost, no Statuse
    assert d.objects["Order"].properties["status"].enum == ["paid", "it's", "b,c"]
    assert set(d.objects["Order"].properties) == {"status"}
    assert d.objects["LineItem"].properties["prio"].enum == ["low", "high"]
    assert d.objects["Status"].source.ref == f"{f}#L9"                               # its CREATE line


@pytest.mark.parametrize("kind,text", [("openapi", "- a\n- b\n"), ("workflow", '"just text"')])
def test_a_document_that_is_not_a_mapping_is_refused_with_a_fix(tmp_path, kind, text):
    with pytest.raises(SystemExit, match="not a mapping. Fix: give the"):
        import_source(kind, _src(tmp_path, "x", text))


@pytest.mark.parametrize("text,msg", [("roles: admin\n", "`roles` is a str. Fix: write it as `roles: \\[a, b\\]`"),
                                      ("- stage_fields\n", "is a list, not a mapping")])
def test_a_profile_value_of_the_wrong_shape_is_refused(tmp_path, text, msg):
    with pytest.raises(SystemExit, match=msg):
        Profile.load(_src(tmp_path, "p.yaml", text))


def test_a_plugged_in_extractor_that_makes_an_invalid_draft_is_stopped():
    class Bad:
        kind = "bad"

        def extract(self, raw, profile):
            return Extraction([Candidate("actions.go", {"description": "Go.", "actor": ["x"]}, "here")])
    register_extractor(Bad())
    with pytest.raises(SystemExit, match="the bad extractor made a draft that does not validate.*Fix: report it"):
        import_source("bad", API)
