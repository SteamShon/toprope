import asyncio
import copy
import http.server
import json
import threading

import pytest
import yaml
from mcp import Client

from toprope.authoring import AuthoringError, Workspace
from toprope.authoring.mcp import build_authoring_server

CONFIG = {"domain": "drafts/d.domain.yaml", "interview_log": "interview/log.jsonl",
          "sources": [{"id": "docs", "kind": "records", "path": "docs"},
                      {"id": "interview", "kind": "interview-log", "path": "interview/log.jsonl"}]}

FULL = {
    "domain": "shop", "version": 1,
    "purpose": {"problem": "Orders get lost.", "success_metric": {"name": "lost orders", "direction": "down"},
                "announcement": "Orders are tracked. None get lost."},
    "roles": ["clerk", "manager"],
    "objects": {"Order": {"description": "A customer order.",
                          "properties": {"status": {"enum": ["open", "shipped"]}, "total": {"type": "number"}}},
                "Customer": {"description": "Who ordered."}},
    "links": {"customer": {"from": "Order", "to": "Customer", "cardinality": "many-to-one"}},
    "actions": {"ship": {"description": "Ship an order.", "actor": ["clerk"], "target": "Order"},
                "reopen": {"description": "Reopen an order.", "actor": ["manager"], "target": "Order"}},
    "transitions": {"Order": {"field": "status", "initial": "open", "matrix": {
        "open": {"ship": "shipped", "reopen": "n/a"},
        "shipped": {"ship": {"deny": "Already shipped."}, "reopen": "open"}}}},
    "invariants": [{"id": "has-total", "on": "Order", "check": "exists(target.total)", "reason": "Every order has a total."}],
    "world": {"fixtures": [{"Customer": {"id": "C1"}}, {"Order": {"id": "O1", "status": "open", "total": 10, "customer": "C1"}}],
              "actors": {"clerk": ["kim"], "manager": ["lee"]}},
    "scenarios": [{"id": "ship-once", "given": {"from_world": "O1"}, "steps": [
        {"actor": {"role": "clerk"}, "do": "ship", "target": "O1", "expect": {"state": {"O1.status": "shipped"}}},
        {"actor": {"role": "clerk"}, "do": "ship", "target": "O1", "expect": {"denied_by": "matrix"}}]}],
    "glossary": {"order": "What a customer asks for."},
}
ORDER = ["sources", "purpose", "cast", "actions", "transitions", "invariants", "world", "handoffs", "review"]


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(CONFIG))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "shop.md").write_text("# Shop\nClerks ship orders. Managers can reopen.\n")
    return Workspace(tmp_path)


def put(ws, doc):
    ws.domain_path.parent.mkdir(parents=True, exist_ok=True)
    ws.domain_path.write_text(yaml.safe_dump(doc, sort_keys=False))


def upto(stage: str) -> dict:
    """FULL, with every part from `stage` on removed."""
    doc = copy.deepcopy(FULL)
    drop = {"purpose": ["purpose"], "cast": ["roles", "objects", "links"], "actions": ["actions"],
            "transitions": ["transitions"], "invariants": ["invariants"], "world": ["world", "scenarios"],
            "review": ["glossary"]}
    for st in ORDER[ORDER.index(stage):]:
        for k in drop.get(st, []):
            doc.pop(k, None)
    if "transitions" not in doc:
        doc.pop("invariants", None)
    return doc


def current(ws):
    return ws.questions(limit=50)["stage"]


def test_stages_advance_in_the_order_the_declaration_depends_on(tmp_path):
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({**CONFIG, "sources": []}))
    empty = Workspace(tmp_path)
    assert current(empty) == "sources"
    assert empty.questions()["questions"][0]["kind"] == "sources"


def test_each_stage_is_current_until_its_part_is_filled(ws):
    for stage in ["purpose", "cast", "actions", "transitions", "invariants", "world"]:
        put(ws, upto(stage))
        assert current(ws) == stage, stage
    put(ws, FULL)
    assert current(ws) == "handoffs"                  # optional, not yet skipped
    ws.skip_stage("handoffs", "Shop hands nothing to another domain.")
    assert current(ws) is None                        # nothing proposed: review is done too
    ws.propose("objects.Note", {"description": "A remark."}, "docs:docs/shop.md#L1-L2")
    b = ws.questions()
    assert b["stage"] == "review" and b["questions"][0]["kind"] == "confirm"


def test_progress_reports_every_stage_with_counts(ws):
    put(ws, upto("transitions"))
    p = ws.progress()
    assert p["current"] == "transitions"
    st = {s["stage"]: s for s in p["stages"]}
    assert [st[x]["status"] for x in ORDER] == ["done", "done", "done", "done", "current", "todo", "todo", "todo", "todo"]
    assert st["cast"]["roles"] == 2 and st["cast"]["objects"] == 2 and st["cast"]["links"] == 1
    assert st["purpose"]["filled"] == ["problem", "success_metric", "announcement"]


def test_bundles_ask_for_what_is_missing(ws):
    put(ws, upto("cast"))
    texts = " ".join(q["text"] for q in ws.questions()["questions"])
    assert "Who takes part" in texts and "keep track of" in texts
    doc = upto("actions")
    doc["objects"]["Note"] = {}                               # undescribed and unrelated
    put(ws, doc)
    cast = " ".join(q["text"] for q in ws.questions(stage="cast")["questions"])
    assert "What is a Note" in cast and "How does a Note relate" in cast
    acts = copy.deepcopy(upto("transitions"))
    acts["roles"].append("auditor")
    put(ws, acts)
    assert any("What does the auditor do" in q["text"] for q in ws.questions(stage="actions")["questions"])
    b = ws.questions()
    assert b["stage"] == "transitions" and b["questions"][0]["text"].startswith("What stages does a Order go through")


def test_purpose_questions_only_ask_for_missing_parts(ws):
    doc = upto("purpose")
    doc["purpose"] = {"problem": "Orders get lost."}
    put(ws, doc)
    b = ws.questions()
    assert b["stage"] == "purpose" and len(b["questions"]) == 2


def test_a_later_break_sends_the_interview_back(ws):
    put(ws, upto("world"))
    assert current(ws) == "world"
    doc = upto("world")
    doc["actions"]["ship"]["actor"] = ["courier"]               # unknown role: an actions conflict
    put(ws, doc)
    b = ws.questions()
    assert b["stage"] == "actions" and b["questions"][0]["kind"] == "conflict"


def test_transitions_stage_waits_for_undecided_cells_under_the_stop_rule(ws):
    doc = upto("invariants")
    doc["transitions"]["Order"]["matrix"]["shipped"]["reopen"] = "undecided"
    doc["actions"]["reopen"]["effects"] = [{"set": {"target.total": 0}}]   # effectful: must be decided
    put(ws, doc)
    b = ws.questions()
    assert b["stage"] == "transitions" and b["stop"]["stop"] is False
    assert any(q["kind"] == "row" for q in b["questions"])


def test_only_optional_stages_are_skipped_and_in_the_owners_words(ws):
    put(ws, upto("invariants"))
    with pytest.raises(AuthoringError, match="optional"):
        ws.skip_stage("actions", "no")
    with pytest.raises(AuthoringError, match="owner's reason"):
        ws.skip_stage("invariants", " ")
    p = ws.skip_stage("invariants", "Nothing must always hold beyond the stages.")
    assert {s["stage"]: s["status"] for s in p["stages"]}["invariants"] == "skipped"
    log = [json.loads(x) for x in ws.log_path.read_text().splitlines()]
    assert log[-1]["kind"] == "skip" and log[-1]["reason"].startswith("Nothing must")


def test_a_whole_bundle_is_answered_at_once(ws):
    put(ws, upto("purpose"))
    b = ws.questions()
    out = ws.answer(b["bundle_id"], "Orders get lost between the counter and the truck. Lost orders should "
                    "go to zero. 'Every order is tracked; none get lost.'",
                    [{"path": "purpose", "value": FULL["purpose"]}])
    assert out["applied"] == ["purpose"] and current(ws) == "cast"
    entry = json.loads(ws.log_path.read_text().splitlines()[-1])
    assert entry["question_id"] == b["bundle_id"] and entry["question"].startswith("[Purpose]")


# -- link sources ------------------------------------------------------------------------------
class Pages(http.server.BaseHTTPRequestHandler):
    PAGES = {"/process": ("text/html", "<html><head><style>x{}</style></head><body><h1>Process</h1>"
                          "<p>Clerks ship.</p><p>Mail ana@example.com</p><script>evil()</script></body></html>"),
             "/notes.txt": ("text/plain", "# Notes\nManagers reopen.\n"),
             "/image": ("image/png", "PNG")}

    def do_GET(self):
        page = self.PAGES.get(self.path)
        if page is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", page[0])
        self.end_headers()
        self.wfile.write(page[1].encode())

    def log_message(self, *a):
        pass


@pytest.fixture
def site(monkeypatch):
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(v, raising=False)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Pages)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def link_ws(tmp_path, site, **extra):
    cfg = {**CONFIG, "sources": [{"id": "wiki", "kind": "records", "url": f"{site}/process", **extra},
                                 {"id": "notes", "kind": "records", "url": f"{site}/notes.txt"},
                                 {"id": "gone", "kind": "records", "url": f"{site}/missing"},
                                 {"id": "pic", "kind": "records", "url": f"{site}/image"}]}
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(cfg))
    return Workspace(tmp_path)


def test_link_sources_are_fetched_once_into_redacted_snapshots(tmp_path, site):
    ws = link_ws(tmp_path, site)
    assert ws.chunks("wiki") == []                                    # not fetched yet
    (meta,) = ws.fetch("wiki")
    assert meta["url"].endswith("/process") and len(meta["sha256"]) == 64
    chunk = ws.read_source("wiki")["chunks"][0]
    assert chunk["ref"] == "wiki:.toprope/snapshots/wiki/snapshot.md#L1-L3"
    assert "Clerks ship." in chunk["text"] and "evil" not in chunk["text"] and "x{}" not in chunk["text"]
    assert "[REDACTED:email]" in chunk["text"]
    ws.fetch("notes")
    assert ws.source_of(ws.chunks("notes")[0].ref)["kind"] == "record"
    listed = {s["id"]: s for s in ws.list_sources()}
    assert listed["wiki"]["fetched"]["sha256"] == meta["sha256"] and listed["gone"]["fetched"] is None


def test_unfetchable_links_say_why(tmp_path, site):
    ws = link_ws(tmp_path, site)
    with pytest.raises(AuthoringError, match="behind a login"):
        ws.fetch("gone")
    with pytest.raises(AuthoringError, match="not text"):
        ws.fetch("pic")
    bad = {**CONFIG, "sources": [{"id": "x", "kind": "records", "url": "file:///etc/passwd"}]}
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(bad))
    with pytest.raises(AuthoringError, match="http"):
        Workspace(tmp_path).fetch("x")
    both = {**CONFIG, "sources": [{"id": "y", "kind": "records", "url": f"{site}/notes.txt", "path": "docs"}]}
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(both))
    with pytest.raises(AuthoringError, match="either a path or a url"):
        Workspace(tmp_path)


def test_a_local_only_link_is_fetched_but_never_served(tmp_path, site):
    ws = link_ws(tmp_path, site, local_only=True)
    ws.fetch("wiki")
    assert len(ws.chunks("wiki")) == 1
    with pytest.raises(AuthoringError, match="local-only"):
        ws.read_source("wiki")


def test_mcp_exposes_stages_progress_and_skip(ws):
    put(ws, upto("invariants"))

    async def go():
        async with Client(build_authoring_server(ws)) as c:
            def p(r):
                sc = r.structured_content
                return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
            b = p(await c.call_tool("questions", {}))
            assert b["stage"] == "invariants" and b["optional"] is True
            assert p(await c.call_tool("progress", {}))["current"] == "invariants"
            out = p(await c.call_tool("skip_stage", {"stage": "invariants", "reason": "None beyond the stages."}))
            assert out["current"] == "world"
            r = await c.call_tool("skip_stage", {"stage": "cast", "reason": "x"})
            assert r.is_error
    asyncio.run(go())
