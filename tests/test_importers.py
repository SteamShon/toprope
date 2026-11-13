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
    assert "questions for the interview:" in text and valid(yaml.safe_load(dest.read_text()))
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
    with pytest.raises(SystemExit, match="the bad extractor made a draft that does not validate.*Fix: .*report it to the extractor"):
        import_source("bad", API)


# A1b: written rules → candidate rules and contradictions (questions, never rules by themselves).

RULES = EX / "rules"


def test_written_rules_become_questions_citing_file_and_line_and_code_is_skipped():
    out = import_source("rules", str(RULES / "AGENTS.md"))
    assert not out["draft"]["objects"] and not out["draft"]["actions"]          # nothing becomes a rule by itself
    qs = out["questions"]
    agents = str(RULES / "AGENTS.md")
    assert any(q.startswith(f"[never] {agents}#L5: “Never push a release tag to `main` by hand.”") for q in qs)
    assert any(q.startswith(f"[must] {agents}#L8: “A refund over 500 EUR must be approved") for q in qs)
    assert any(q.startswith(f"[only] {agents}#L16: “Schema change — the data owner only”") for q in qs)
    assert not any("git push origin main" in q for q in qs)                     # inside a code fence
    assert not any("tags `main` after the checks pass" in q for q in qs)        # binds no one


def test_a_folder_of_skill_files_is_read_together_and_contradictions_name_both_places():
    out = import_source("rules", str(RULES), via="tree")
    agents, skill = str(RULES / "AGENTS.md"), str(RULES / "skills/hotfix/SKILL.md")
    assert out["conflicts"] == [f"{skill}#L8 says “When production is down, always push the release tag to `main` by "
                                f"hand so the fix ships at once.”, but {agents}#L5 says “Never push a release tag to "
                                "`main` by hand.”"]
    assert not any("Never use for features" in q for q in out["questions"])     # front matter is skipped


def test_rules_do_not_conflict_by_sharing_a_word_or_two():
    out = import_source("rules", str(RULES), via="tree")
    assert not any("Refunds stay" in c for c in out["conflicts"])               # "refund" alone is not a contradiction


def test_this_repositorys_own_agents_md_gives_candidates_and_no_false_conflicts():
    out = import_source("rules", str(EX.parents[1] / "AGENTS.md"))
    assert len(out["questions"]) >= 30 and not out["conflicts"]
    assert any("Never commit or push directly to `main` or `develop`." in q for q in out["questions"])


def test_the_command_reports_rules_without_writing_a_draft_and_saves_the_questions(tmp_path, capsys):
    q = tmp_path / "q.yaml"
    main(["rules", str(RULES), "--via", "tree", "--questions", str(q), "--out", str(tmp_path / "d.yaml")])
    text = capsys.readouterr().out
    assert "no draft written" in text and "conflicts in the source:" in text and not (tmp_path / "d.yaml").exists()
    saved = yaml.safe_load(q.read_text())
    assert len(saved["conflicts"]) == 1 and saved["questions"]
    with pytest.raises(SystemExit, match="is not a folder. Fix: give a folder"):
        import_source("rules", str(RULES / "AGENTS.md"), via="tree")


# Review of #228 (2026-11-10): each case below gave a wrong citation, a lost or wrong rule, a
# false conflict, a file read outside the folder, or a file written by a run that failed.

def _rules_of(tmp_path, text, name="AGENTS.md"):
    out = import_source("rules", _src(tmp_path, name, text))
    return out, {q.split(": “", 1)[1].split("” Which")[0]: q.split("]")[0][1:] + " " + q.split(" ")[1].rsplit("#", 1)[1].rstrip(":")
                 for q in out["questions"]}


def test_citations_and_text_survive_bold_and_code_spans(tmp_path):
    _, r = _rules_of(tmp_path, "**a** **b** __c__ z.\nYou must test.\nNever edit `__init__.py` by hand.\n")
    assert r["You must test."] == "must L2"
    assert r["Never edit `__init__.py` by hand."] == "never L3"


def test_a_negation_anywhere_in_the_sentence_wins(tmp_path):
    out, r = _rules_of(tmp_path, "Agents must never push to main.\n\nNo agent may merge a release.\n\n"
                                 "Before 2020 the team used SVN.\n\nYou should run the checks.\n")
    assert r["Agents must never push to main."].startswith("never")
    assert r["No agent may merge a release."].startswith("never")
    assert r["You should run the checks."].startswith("must")
    assert "Before 2020 the team used SVN." not in r


def test_a_marker_line_in_a_file_is_only_text(tmp_path):
    _, r = _rules_of(tmp_path, "You must A.\n<!-- toprope:file /etc/passwd -->\nYou must B.\n")
    assert r["You must A."] == "must L1" and r["You must B."] == "must L3"


def test_markdown_that_is_not_prose_is_skipped_and_prose_is_kept(tmp_path):
    _, r = _rules_of(tmp_path, """---

You must keep the opening rule.

---
A wrapped line names
#91 which must be fixed.

~~~
``` you must not read this
~~~

<!-- a comment
you must not read this either -->
Indented code follows.

    rm -rf / # you must not run

> Quoted: you must read quotes.

| Who | Rule |
|---|---|
| ops | `a | b` must hold |
""")
    assert "You must keep the opening rule." in r                                 # `---` is a break, not front matter
    assert r["A wrapped line names #91 which must be fixed."] == "must L6"
    assert not [k for k in r if "read this" in k or "rm -rf" in k]
    assert r["Quoted: you must read quotes."] == "must L19"
    assert r["ops — `a | b` must hold"] == "must L23"


def test_two_shared_words_are_not_a_contradiction_and_a_flood_is_capped(tmp_path):
    out, _ = _rules_of(tmp_path, "Never commit secrets to the repository.\n\nAlways commit the lockfile to the repository.\n\n"
                                 "Never merge a PR without review.\n\nAlways merge a PR with squash after review.\n")
    assert out["conflicts"] == []
    flood = "\n\n".join(f"Never push tag {i} to main.\n\nAlways push tag {i} to main." for i in range(15))
    out, _ = _rules_of(tmp_path, flood, "flood.md")
    assert len(out["conflicts"]) == 101 and out["conflicts"][-1].startswith("… and ")


def test_the_tree_reader_stays_inside_its_folder_and_out_of_hidden_ones(tmp_path):
    root = tmp_path / "docs"
    (root / ".venv").mkdir(parents=True)
    (root / ".venv" / "x.md").write_text("You must not see this.")
    (root / "a.md").write_text("You must see this.")
    (tmp_path / "outside.md").write_text("You must not see this either.")
    out = import_source("rules", str(root), via="tree")
    assert [q for q in out["questions"] if "see" in q] == [f"[must] {root / 'a.md'}#L1: “You must see this.” Which "
                                                           "action, rule or role is this, and who enforces it?"]
    for glob in ("../*.md", "/etc/*"):
        with pytest.raises(SystemExit, match="reaches outside .*Fix: give a pattern inside the folder"):
            import_source("rules", str(root), via="tree", profile=Profile(options={"glob": glob}))


def test_a_run_that_fails_writes_nothing(tmp_path):
    q, d = tmp_path / "q.yaml", tmp_path / "d.yaml"
    d.write_text("taken")
    with pytest.raises(SystemExit, match="d.yaml exists"):
        main(["openapi", API, "--out", str(d), "--questions", str(q)])
    assert not q.exists()
    with pytest.raises(SystemExit, match="name the same file"):
        main(["openapi", API, "--out", str(q), "--questions", str(q)])
    assert not q.exists()
    with pytest.raises(SystemExit, match="nothing to import"):
        main(["rules", _src(tmp_path, "empty.md", "# Just a heading\n"), "--questions", str(q)])
    assert not q.exists()


# Review of theme 4 (2026-11-10): an import did not reach an enforced declaration without hand work.

def test_questions_and_conflicts_are_records_naming_what_they_decide_and_where(tmp_path):
    out = import_source("openapi", API, domain="shop")
    who = next(n for n in out["question_records"] if n.kind == "actor" and "refund_order" in n.text)
    assert who.decides == ["actions.refund_order.actor"]
    assert who.places == [f"{API}#/paths/~1orders~1{{id}}~1refund/post"]
    assert [n.text for n in out["question_records"]] == out["questions"]         # the strings stay, one record each
    rules = import_source("rules", str(RULES), via="tree")
    (c,) = rules["conflict_records"]
    agents, skill = str(RULES / "AGENTS.md"), str(RULES / "skills/hotfix/SKILL.md")
    assert c.kind == "contradiction" and c.places == [f"{skill}#L8", f"{agents}#L5"]
    assert c.modality == ["must", "never"] and c.quote[1] == "Never push a release tag to `main` by hand."
    rule = next(n for n in rules["question_records"] if n.places == [f"{agents}#L5"])
    assert rule.kind == "rule" and rule.modality == "never" and rule.quote == "Never push a release tag to `main` by hand."
    assert {"push", "release", "tag"} <= set(rule.terms)


def test_the_command_writes_question_records_an_agent_can_put_in_the_interview(tmp_path):
    q = tmp_path / "q.yaml"
    main(["openapi", API, "--domain", "shop", "--out", str(tmp_path / "d.yaml"), "--questions", str(q)])
    saved = yaml.safe_load(q.read_text())
    rec = next(r for r in saved["questions"] if r["kind"] == "actor" and "refund_order" in r["text"])
    assert rec["id"].startswith("Q-import-") and rec["decides"] == ["actions.refund_order.actor"]
    assert rec["places"] == [f"{API}#/paths/~1orders~1{{id}}~1refund/post"]


def test_a_second_source_joins_a_draft_and_a_disagreement_is_a_conflict_not_an_overwrite(tmp_path, capsys):
    dest = tmp_path / "shop.domain.yaml"
    main(["openapi", API, "--domain", "shop", "--out", str(dest)])
    with pytest.raises(SystemExit, match="exists. Fix: give --out a new file, or --into it"):
        main(["sql", SQL, "--out", str(dest)])
    main(["sql", SQL, "--into", str(dest)])
    d = valid(yaml.safe_load(dest.read_text()))
    order = d.objects["Order"]
    assert order.properties["channel"].enum == ["web", "store"] and "placed_at" in order.properties   # both sources
    assert order.source.ref == f"{SQL}#L3" and order.status == "proposed"       # changed, so proposed again
    assert set(d.actions) == {"create_order", "refund_order"}
    other = _src(tmp_path, "other.sql", "CREATE TABLE orders (status text CHECK (status IN ('open', 'closed')));\n")
    main(["sql", other, "--into", str(dest)])
    text = capsys.readouterr().out
    assert "objects.Order.properties.status: the draft has" in text and f"{other}#L1" in text
    d = valid(yaml.safe_load(dest.read_text()))
    assert d.objects["Order"].properties["status"].enum == ["paid", "shipped", "refunded"]   # kept the draft's
    assert d.transitions["Order"].matrix.keys() == {"paid", "shipped", "refunded"}


def _tools(*tools):
    return Raw(json.dumps({"server": {"command": ["python", "server.py"]}, "tools": list(tools)}).encode(), "srv")


ORDER_OUT = {"type": "object", "required": ["status", "total"], "properties": {
    "order_id": {"type": "string"}, "status": {"enum": ["paid", "refunded"], "type": "string"},
    "total": {"type": "number"}, "refund_id": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}
REFUND = {"name": "refund_order", "description": "Refund an order.",
          "inputSchema": {"type": "object", "required": ["order_id", "amount"], "properties": {
              "order_id": {"type": "string"}, "amount": {"type": "number"},
              "note": {"anyOf": [{"type": "string"}, {"type": "null"}]}, "lines": {"type": "array"}}},
          "outputSchema": {"type": "object", "properties": {"refund_id": {"type": "string"}}}}
GET = {"name": "get_order", "inputSchema": {"type": "object", "properties": {"order_id": {"type": "string"}}},
       "outputSchema": ORDER_OUT, "annotations": {"readOnlyHint": True}}
WIPE = {"name": "wipe_orders", "inputSchema": {"type": "object", "properties": {}}}


def test_a_servers_tools_become_proposed_actions_with_their_call_and_reply_and_a_draft_binding():
    from toprope.importers.draft import build
    from toprope.importers.extractors.mcp import McpExtractor, render_binding
    ext = McpExtractor().extract(_tools(REFUND, GET, WIPE), Profile())
    d = valid(build("payments", ext))
    a = d.actions["refund_order"]
    assert a.target == "Order" and a.actor == ["unassigned"] and a.status == "proposed"
    assert a.params["amount"].type == "number" and a.params["note"].optional and "lines" not in a.params
    (e,) = a.effects
    assert e.call == "mcp:refund_order" and e.reply == "record_refund_order"
    assert e.with_ == {"order_id": "target.id", "amount": "params.amount", "note": "params.note"}
    r = d.actions["record_refund_order"]
    assert r.actor == ["external:kernel"] and set(r.params) == {"ok", "refund_id"}
    assert r.preconditions[0].check == "params.ok == true"
    assert r.effects[0].set == {"target.refund_id": "params.refund_id"}           # a fact the thing keeps
    assert set(d.objects["Order"].properties) == {"status", "total", "refund_id"}  # from get_order's output schema
    m = d.transitions["Order"].matrix
    assert m["paid"]["refund_order"] == "undecided" and m["refunded"]["record_refund_order"] == "undecided"
    assert "wipe_orders" not in d.actions
    b = yaml.safe_load(render_binding(ext.binding, "payments"))
    assert "confirmed" not in b and b["upstream"] == {"command": ["python", "server.py"]}
    assert b["tools"] == {"refund_order": {"action": "refund_order", "target": "order_id",
                                           "result": {"refund_id": "string"}, "load": "get_order"},
                          "get_order": {"read": True}}
    kinds_asked = {n.kind: n for n in ext.question_records()}
    assert {"actor", "target", "param", "cell", "stage"} <= set(kinds_asked)
    assert kinds_asked["target"].decides == ["actions.wipe_orders"] and kinds_asked["target"].places == ["srv#/tools/2"]
    assert "transitions.Order.matrix.paid.record_refund_order" in kinds_asked["cell"].decides


def test_openapi_asks_how_a_thing_is_created_and_drafts_a_call_only_when_it_is_named(tmp_path):
    api = yaml.safe_load(Path(API).read_text())
    del api["paths"]["/orders"], api["components"]["schemas"]["NewOrder"]
    api["paths"]["/orders/{id}/refund"]["post"]["x-toprope-call"] = "mcp:refund_order"
    f = tmp_path / "api.yaml"
    f.write_text(yaml.safe_dump(api))
    out = import_source("openapi", str(f), domain="shop")
    d = valid(out["draft"])
    (e,) = d.actions["refund_order"].effects
    assert e.call == "mcp:refund_order" and e.with_ == {"id": "target.id", "reason": "params.reason",
                                                         "amount": "params.amount"}
    assert d.actions["record_refund_order"].actor == ["external:kernel"]
    assert d.transitions["Order"].matrix["paid"]["record_refund_order"] == "undecided"
    created = [n for n in out["question_records"] if n.kind == "creation"]
    assert [n.decides[0] for n in created] == ["objects.Order"]
    plain = import_source("openapi", API, domain="shop")
    assert not valid(plain["draft"]).actions["refund_order"].effects                  # no call named: asked instead
    assert {n.decides[0] for n in plain["question_records"] if n.kind == "call"} == {
        "actions.refund_order.effects", "actions.create_order.effects"}
    assert not [n for n in plain["question_records"] if n.kind == "creation"]       # createOrder creates it


def test_a_draft_no_one_may_act_in_is_reported_as_not_ready(tmp_path, capsys):
    from toprope.harness.cli import main as harness
    d = valid(import_source("openapi", API, domain="shop")["draft"])
    warned = [i for i in validate_domain(d) if i.code == "unassigned-actor"]
    assert {i.where for i in warned} == {"actions.create_order.actor", "actions.refund_order.actor"}
    assert all(i.severity == "warning" and "Fix: answer who may take it" in i.message for i in warned)
    f = tmp_path / "shop.domain.yaml"
    main(["openapi", API, "--domain", "shop", "--out", str(f)])
    with pytest.raises(SystemExit):
        harness(["--domain", str(f), "--levels", "model", "--examples", "0"])
    assert "not ready: 2 of 2 action(s) no one may take yet" in capsys.readouterr().out


# Review of #240 (2026-11-10): camelCase arguments, typed enums, and guessing the thing.

def _drafted(*tools):
    from toprope.importers.draft import build
    from toprope.importers.extractors.mcp import McpExtractor
    ext = McpExtractor().extract(_tools(*tools), Profile())
    return valid(build("shop", ext)), ext


def test_a_camel_case_argument_is_mapped_in_the_binding_and_passed_on_under_its_own_name():
    cancel = {"name": "cancel_order", "inputSchema": {"type": "object", "required": ["orderId", "reasonCode"],
                                                      "properties": {"orderId": {"type": "string"},
                                                                     "reasonCode": {"type": "string"}}}}
    d, ext = _drafted(cancel)
    a = d.actions["cancel_order"]
    assert a.target == "Order" and set(a.params) == {"reason_code"}
    assert a.effects[0].with_ == {"orderId": "target.id", "reasonCode": "params.reason_code"}
    assert ext.binding["tools"]["cancel_order"]["target"] == "orderId"
    assert ext.binding["tools"]["cancel_order"]["params"] == {"reason_code": "reasonCode"}


def test_numbers_in_an_enum_keep_their_type_and_are_asked_about():
    get = {"name": "get_ticket", "annotations": {"readOnlyHint": True},
           "inputSchema": {"type": "object", "properties": {"ticket_id": {"type": "string"}}},
           "outputSchema": {"type": "object", "required": ["priority"], "properties": {
               "priority": {"type": "integer", "enum": [1, 2, 3]}}}}
    close = {"name": "close_ticket", "inputSchema": {"type": "object", "required": ["ticket_id", "level"],
                                                     "properties": {"ticket_id": {"type": "string"},
                                                                    "level": {"enum": [0.5, 1]}}}}
    d, ext = _drafted(get, close)
    assert d.objects["Ticket"].properties["priority"].type == "integer"     # never the names "1", "2", "3"
    assert d.actions["close_ticket"].params["level"].type == "number"
    asked = [n for n in ext.question_records() if "[1, 2, 3]" in n.text or "[0.5, 1]" in n.text]
    assert [n.decides for n in asked] == [["actions.close_ticket.params.level"],
                                          ["objects.Ticket.properties.priority"]]
    out = import_source("openapi", _src_api({"type": "integer", "enum": [1, 2]}), domain="shop")
    assert valid(out["draft"]).objects["Order"].properties["prio"].type == "integer"


def _src_api(prio):
    import tempfile
    f = Path(tempfile.mkdtemp()) / "a.yaml"
    f.write_text(yaml.safe_dump({"paths": {}, "components": {"schemas": {"Order": {
        "type": "object", "properties": {"prio": prio}}}}}))
    return str(f)


def test_the_thing_is_a_whole_word_of_the_tool_and_a_server_assigned_id_is_asked_about():
    reorder = {"name": "reorder_item", "inputSchema": {"type": "object", "properties": {
        "order_id": {"type": "string"}, "item_id": {"type": "string"}}}}
    create = {"name": "create_order", "inputSchema": {"type": "object", "properties": {
        "customer": {"type": "string"}, "total": {"type": "number"}}}}
    bare = {"name": "archive_invoice", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}}}
    d, ext = _drafted(reorder, create, bare)
    assert d.actions["reorder_item"].target == "Item"                       # not Order, inside "reorder"
    assert "create_order" not in d.actions and "create_order" not in ext.binding["tools"]
    asked = {n.kind: n for n in ext.question_records() if "create_order" in n.text or "archive_invoice" in n.text}
    assert "whose id the server assigns" in asked["creation"].text and "objects.Order" in asked["creation"].decides
    assert d.actions["archive_invoice"].target == "Invoice"
    assert "guessed Invoice from the tool's name" in asked["target"].text


def test_joining_a_source_that_names_who_acts_fills_an_unassigned_actor(tmp_path, capsys):
    dest = tmp_path / "shop.domain.yaml"
    main(["openapi", API, "--domain", "shop", "--out", str(dest)])
    api = yaml.safe_load(Path(API).read_text())
    api["paths"]["/orders/{id}/refund"]["post"]["x-roles"] = ["clerk"]
    f = _src(tmp_path, "roles.yaml", yaml.safe_dump(api))
    prof = _src(tmp_path, "p.yaml", "roles_from: x-roles\n")
    capsys.readouterr()
    main(["openapi", f, "--into", str(dest), "--profile", prof])
    text = capsys.readouterr().out
    assert "0 conflict(s)" in text and "actions.refund_order" not in text.split("conflicts")[0]
    d = valid(yaml.safe_load(dest.read_text()))
    assert d.actions["refund_order"].actor == ["clerk"] and d.actions["refund_order"].status == "proposed"
    assert d.actions["create_order"].actor == ["unassigned"] and "clerk" in d.roles


# -- an MCP server that needs its keys to start (M2: Alpaca's server) ------------------------------

KEYED_SERVER = '''
import os, sys
if not os.environ.get("SERVER_KEY") or os.environ.get("MODE") != "paper":
    sys.exit("SERVER_KEY must be set, and MODE must be paper")
from mcp.server.mcpserver import MCPServer
server = MCPServer(name="keyed")

@server.tool(description="Cancel an order.")
def cancel_order(order_id: str) -> dict:
    return {"order_id": order_id}

server.run()
'''


def test_an_mcp_server_that_needs_keys_is_imported_with_env_and_pass_env(tmp_path, monkeypatch):
    """The server gets `--env` values and the named variables from the importer's environment; the
    draft binding names them as the proxy reads them, and holds no secret value."""
    import sys

    from toprope.importers.cli import main
    script = tmp_path / "keyed_server.py"
    script.write_text(KEYED_SERVER)
    monkeypatch.setenv("SERVER_KEY", "s3cret-value")
    out, binding = tmp_path / "d.yaml", tmp_path / "b.yaml"
    main(["mcp", f"{sys.executable} {script}", "--domain", "keyed", "--out", str(out), "--binding-out", str(binding),
          "--env", "MODE=paper", "--pass-env", "SERVER_KEY"])
    assert "cancel_order" in yaml.safe_load(out.read_text())["actions"]
    text = binding.read_text()
    up = yaml.safe_load(text)["upstream"]
    assert up == {"command": [sys.executable, str(script)], "env": {"MODE": "paper"}, "pass_env": ["SERVER_KEY"]}
    assert "s3cret-value" not in text and "s3cret-value" not in out.read_text()


def test_env_and_pass_env_are_refused_where_they_cannot_apply(tmp_path, monkeypatch):
    from toprope.importers.cli import main
    monkeypatch.delenv("NOT_SET_ANYWHERE", raising=False)
    with pytest.raises(SystemExit, match="--env"):
        main(["openapi", str(tmp_path / "x.yaml"), "--env", "A=1"])
    with pytest.raises(SystemExit, match="NAME=VALUE"):
        main(["mcp", "srv", "--env", "A"])
    with pytest.raises(SystemExit, match="NOT_SET_ANYWHERE"):
        main(["mcp", "srv", "--pass-env", "NOT_SET_ANYWHERE"])
