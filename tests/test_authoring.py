import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from mcp import Client, types
from mcp.shared.exceptions import MCPError

from test_decl import schema_doc_domain
from toprope.authoring import AuthoringError, Workspace
from toprope.authoring.mcp import build_authoring_server
from toprope.sources import SourceSpec, read, redact

FAKE_GH = "ghp_" + "a" * 36
FAKE_KEY = "sk-ant-" + "b" * 30


# -- redaction -------------------------------------------------------------------------------
@pytest.mark.parametrize("text,kind", [
    (f"token {FAKE_GH} here", "github-token"),
    (f"ANTHROPIC={FAKE_KEY}", "api-key"),
    ("AKIAABCDEFGHIJKLMNOP", "aws-key"),
    ("Authorization: Bearer abcdefghijklmnopqrstuvwx", "bearer"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----", "private-key"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbmEifQ.c2lnbmF0dXJlMTIz", "jwt"),
    ("mail ana.kim@example.com please", "email"),
    ("call +82 10-1234-5678 now", "phone"),
    ("rrn 900101-1234567", "resident-id"),
    ("xoxb-1234567890-abcdef", "slack-token"),
])
def test_redaction_removes_secrets_and_personal_data(text, kind):
    out, counts = redact(text)
    assert counts.get(kind) == 1 and f"[REDACTED:{kind}]" in out


def test_redaction_keeps_assignment_names_and_ordinary_text():
    out, counts = redact('password = "hunter22"\nversion 1.2.3 on 2026-11-04, port 8765')
    assert out.startswith("password = [REDACTED:secret]") and counts == {"assignment": 1}
    assert "version 1.2.3 on 2026-11-04, port 8765" in out


# -- a workspace -----------------------------------------------------------------------------
CONFIG = {
    "domain": "drafts/example.domain.yaml",
    "interview_log": "interview/log.jsonl",
    "sources": [
        {"id": "repo", "kind": "repository", "path": "src"},
        {"id": "docs", "kind": "records", "path": "docs"},
        {"id": "sessions", "kind": "transcripts", "path": "sessions", "local_only": True},
        {"id": "interview", "kind": "interview-log", "path": "interview/log.jsonl"},
        {"id": "all", "kind": "records", "path": "."},
    ],
}


@pytest.fixture
def ws(tmp_path) -> Workspace:
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(CONFIG))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("\n".join(f"line {i}" for i in range(1, 201)) + f"\nKEY = '{FAKE_KEY}'\n")
    (tmp_path / "src" / "blob.bin").write_bytes(b"\xff\xfe\x00binary")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "process.md").write_text(
        "# Process\nIntro.\n\n## Approval\nEvery experiment needs an approver. Ask ana.kim@example.com.\n\n"
        "## Launch\nEngineers launch approved experiments.\n")
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "s1.jsonl").write_text(json.dumps(
        {"type": "user", "message": {"role": "user", "content": "PMs never approve."}}) + "\n")
    inst = tmp_path / "experiments" / "m1" / "instruments"
    inst.mkdir(parents=True)
    (inst / "gold.md").write_text("# Gold\nheld-out answer\n")
    (tmp_path / "experiments" / "m1" / "interview-guide.md").write_text("# Guide\nprobed areas\n")
    return Workspace(tmp_path)


def test_readers_chunk_with_stable_refs_and_redact(ws):
    repo = ws.chunks("repo")
    assert [c.ref for c in repo] == ["repo:src/app.py#L1-L120", "repo:src/app.py#L121-L201"]   # binary skipped
    assert "[REDACTED:api-key]" in repo[1].text and FAKE_KEY not in repo[1].text
    docs = ws.chunks("docs")
    assert [c.ref for c in docs] == ["docs:docs/process.md#L1-L3", "docs:docs/process.md#L4-L6",
                                     "docs:docs/process.md#L7-L8"]
    assert "[REDACTED:email]" in docs[1].text
    assert ws.chunks("sessions")[0].text == "user: PMs never approve."


def test_held_out_instruments_are_never_read(ws):
    assert not any("experiments/" in c.ref for c in ws.chunks("all"))
    assert ws.search_sources("probed areas") == []
    assert ws.search_sources("held-out") == []


def test_local_only_sources_are_listed_but_never_served(ws):
    listed = {s["id"]: s for s in ws.list_sources()}
    assert listed["sessions"]["local_only"] is True and listed["sessions"]["chunks"] == 1
    with pytest.raises(AuthoringError, match="local-only"):
        ws.read_source("sessions")
    assert ws.search_sources("PMs never") == []


def test_sources_outside_the_workspace_and_symlinks_are_refused(tmp_path, ws):
    with pytest.raises(ValueError, match="outside"):
        read(SourceSpec("x", "records", "../"), ws.root)
    outside = tmp_path.parent / "secret-outside.md"
    outside.write_text("# Secret\nleak\n")
    (ws.root / "docs" / "link.md").symlink_to(outside)
    assert not any("link.md" in c.ref for c in read(SourceSpec("docs", "records", "docs"), ws.root))


def test_usage_log_records_what_was_served(ws):
    ws.read_source("docs", limit=2)
    ws.search_sources("Engineers")
    used = [json.loads(line) for line in ws.usage_path.read_text().splitlines()]
    assert used[0]["refs"] == ["docs:docs/process.md#L1-L3", "docs:docs/process.md#L4-L6"]
    assert any("docs:docs/process.md#L7-L8" in u["refs"] for u in used[1:])


# -- drafting --------------------------------------------------------------------------------
def test_propose_cites_a_real_chunk_and_is_always_proposed(ws):
    ws.propose("roles", ["approver", "eng"], "docs:docs/process.md#L4-L6")
    out = ws.propose("objects.Experiment", {"description": "A test.", "status": "confirmed"},
                     "docs:docs/process.md#L4-L6", quote="Every experiment needs an approver.")
    assert out["status"] == "proposed"
    el = ws.draft()["objects"]["Experiment"]
    assert el["status"] == "proposed"                                      # an agent cannot confirm
    assert el["source"] == {"kind": "record", "ref": "docs:docs/process.md#L4-L6",
                            "quote": "Every experiment needs an approver."}
    with pytest.raises(AuthoringError, match="no chunk"):
        ws.propose("objects.Ghost", {}, "docs:docs/process.md#L99-L100")
    with pytest.raises(AuthoringError, match="unknown source"):
        ws.propose("objects.Ghost", {}, "nowhere:x#L1")


def test_propose_keeps_the_draft_parseable_and_returns_issues(ws):
    ws.propose("roles", ["approver"], "docs:docs/process.md#L4-L6")
    before = ws.domain_path.read_text()
    with pytest.raises(AuthoringError, match="would not parse"):
        ws.propose("objects.Experiment", {"descripton": "typo"}, "docs:docs/process.md#L4-L6")
    assert ws.domain_path.read_text() == before
    out = ws.propose("actions.approve", {"description": "Approve.", "actor": ["nobody"], "target": "Experiment"},
                     "docs:docs/process.md#L4-L6")
    assert {"unknown-role", "unknown-object"} <= {i["code"] for i in out["issues"]}


def _seed_example(ws):
    """The schema example as the draft, every element proposed from the docs."""
    raw = schema_doc_domain()
    raw.pop("scenarios")
    ws.domain_path.parent.mkdir(parents=True, exist_ok=True)
    ws.domain_path.write_text(yaml.safe_dump(raw, sort_keys=False))


def test_matrix_cells_take_provenance_except_bare_n_a_and_undecided(ws):
    _seed_example(ws)
    ws.propose("transitions.Experiment.matrix.ended.launch_experiment", "running", "docs:docs/process.md#L7-L8")
    ws.propose("transitions.Experiment.matrix.decided.launch_experiment", "n/a", "docs:docs/process.md#L7-L8")
    m = ws.draft()["transitions"]["Experiment"]["matrix"]
    assert m["ended"]["launch_experiment"]["to"] == "running" and m["ended"]["launch_experiment"]["status"] == "proposed"
    assert m["decided"]["launch_experiment"] == "n/a"


# -- interview -------------------------------------------------------------------------------
def test_questions_open_with_purpose_then_defaults_and_grouped_rows(ws):
    _seed_example(ws)
    qs = ws.questions(limit=50)["questions"]
    assert qs[0]["kind"] == "purpose"
    kinds = [q["kind"] for q in qs]
    assert "row" in kinds
    row = next(q for q in qs if q["kind"] == "row")
    assert row["decides"] == ["transitions.Experiment.matrix.ended.launch_experiment"]
    assert "Once a Experiment is ended" in row["text"]


def test_attempts_raise_priority_and_drive_the_stop_rule(ws):
    raw = schema_doc_domain()
    raw.pop("scenarios")
    raw["purpose"] = {"problem": "Ship experiments safely."}
    for s in ("ended", "decided"):   # leave two cells undecided for launch, none for approve
        raw["transitions"]["Experiment"]["matrix"][s]["launch_experiment"] = "undecided"
    raw["actions"]["launch_experiment"]["effects"] = []
    ws.domain_path.parent.mkdir(parents=True, exist_ok=True)
    ws.domain_path.write_text(yaml.safe_dump(raw, sort_keys=False))
    calm = ws.questions(limit=50, attempts={})
    assert calm["stop"]["stop"] is True                         # nothing attempted, no effects
    hot = ws.questions(limit=50, attempts={"launch_experiment": 3})
    assert hot["stop"]["stop"] is False and len(hot["stop"]["open"]) == 2
    assert hot["questions"][0]["kind"] == "default" and hot["questions"][0]["priority"] >= 300


def test_attempts_are_read_from_the_configured_event_store(ws, tmp_path):
    from toprope.decl import Domain
    from toprope.semantics import Actor, Command, ReferenceModel
    from toprope.store.sqlite import SQLiteEventStore
    m = ReferenceModel(Domain.model_validate(schema_doc_domain()), SQLiteEventStore(str(tmp_path / "ev.db")))
    m.seed("Experiment", {"id": "E-x", "status": "ended", "planned_days": 1, "guardrails": []})
    m.execute(Command(Actor("eli", "person", ("eng",)), "launch_experiment", "E-x"))
    cfg = {**CONFIG, "event_store": "sqlite:ev.db"}
    (ws.root / "toprope.workspace.yaml").write_text(yaml.safe_dump(cfg))
    assert Workspace(ws.root).attempts_by_action() == {"launch_experiment": 1}


def test_answer_records_the_owners_words_and_cites_them(ws):
    _seed_example(ws)
    row = next(q for q in ws.questions(limit=50)["questions"] if q["kind"] == "row")
    out = ws.answer(row["id"], "No. Once it has ended it never relaunches.",
                    [{"path": "transitions.Experiment.matrix.ended.launch_experiment",
                      "value": {"deny": "An ended experiment never relaunches."}}])
    assert out["ref"] == "interview:interview/log.jsonl#L1"
    cell = ws.draft()["transitions"]["Experiment"]["matrix"]["ended"]["launch_experiment"]
    assert cell["source"] == {"kind": "interview", "ref": "interview:interview/log.jsonl#L1",
                              "quote": "No. Once it has ended it never relaunches."}
    assert cell["status"] == "proposed"
    assert ws.chunks("interview")[0].ref == "interview:interview/log.jsonl#L1"   # citable afterwards
    assert not any(q["kind"] == "row" for q in ws.questions(limit=50)["questions"])
    with pytest.raises(AuthoringError, match="owner's words"):
        ws.answer(row["id"], "  ", [])


def test_only_a_human_channel_confirms(ws):
    _seed_example(ws)
    ws.propose("objects.Readout", {"description": "Result."}, "docs:docs/process.md#L7-L8")
    with pytest.raises(AuthoringError, match="only a person"):
        ws.confirm(["objects.Readout"], via="agent")
    with pytest.raises(AuthoringError, match="not a drafted element"):
        ws.confirm(["roles"], via="cli")
    ws.confirm(["objects.Readout"], via="cli", who="owner")
    assert ws.draft()["objects"]["Readout"]["status"] == "confirmed"
    log = [json.loads(line) for line in ws.log_path.read_text().splitlines()]
    assert log[-1] == {**log[-1], "kind": "confirm", "paths": ["objects.Readout"], "via": "cli"}


def test_cli_confirm_needs_the_owners_terminal(ws):
    _seed_example(ws)
    ws.propose("objects.Readout", {"description": "Result."}, "docs:docs/process.md#L7-L8")
    base = ["uv", "run", "--quiet", "toprope-author", "confirm", "objects.Readout", "--workspace", str(ws.root)]
    r = subprocess.run(base, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    assert r.returncode != 0 and "terminal" in r.stderr
    assert ws.draft()["objects"]["Readout"]["status"] == "proposed"
    r = subprocess.run(base + ["--yes"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and ws.draft()["objects"]["Readout"]["status"] == "confirmed"


def test_check_runs_the_harness_on_the_draft(ws):
    _seed_example(ws)
    out = ws.check()
    assert out["parses"] and out["harness"]["ok"] and out["matrix"]["undecided"] == 1


# -- the authoring MCP ---------------------------------------------------------------------------
def _p(res):
    sc = res.structured_content
    return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc


def test_authoring_mcp_flow_and_confirmation_by_elicitation(ws):
    _seed_example(ws)
    ws.propose("objects.Readout", {"description": "Result."}, "docs:docs/process.md#L7-L8")
    asked = []

    async def owner_accepts(ctx, params):
        asked.append(params.message)
        return types.ElicitResult(action="accept", content={"confirm": True})

    async def owner_declines(ctx, params):
        return types.ElicitResult(action="decline")

    async def go():
        server = build_authoring_server(ws)
        async with Client(server) as c:
            srcs = {s["id"]: s for s in _p(await c.call_tool("list_sources", {}))}
            assert srcs["sessions"]["local_only"]
            r = await c.call_tool("read_source", {"source_id": "sessions"})
            assert r.is_error and "local-only" in r.content[0].text
            chunk = _p(await c.call_tool("read_source", {"source_id": "docs", "limit": 1}))["chunks"][0]
            out = _p(await c.call_tool("propose", {"path": "links.readout_of", "value": {
                "from": "Readout", "to": "Experiment", "cardinality": "many-to-one"}, "source_ref": chunk["ref"]}))
            assert out["status"] == "proposed"
            q = _p(await c.call_tool("questions", {"limit": 3}))
            assert q["questions"][0]["kind"] == "purpose"
            with pytest.raises(MCPError, match="elicitation"):              # the client cannot ask the owner
                await c.call_tool("confirm", {"paths": ["objects.Readout"]})
            tools = {t.name: t for t in (await c.list_tools()).tools}
            assert "toprope-author confirm" in tools["confirm"].description
        async with Client(server, elicitation_callback=owner_declines) as c:
            assert _p(await c.call_tool("confirm", {"paths": ["objects.Readout"]}))["confirmed"] == []
        assert ws.draft()["objects"]["Readout"]["status"] == "proposed"
        async with Client(server, elicitation_callback=owner_accepts) as c:
            assert _p(await c.call_tool("confirm", {"paths": ["objects.Readout"]}))["confirmed"] == ["objects.Readout"]
    asyncio.run(go())
    assert "objects.Readout" in asked[0]
    assert ws.draft()["objects"]["Readout"]["status"] == "confirmed"
    assert json.loads(ws.log_path.read_text().splitlines()[-1])["via"] == "elicitation"


def test_cli_init_writes_a_starter_workspace(tmp_path):
    r = subprocess.run(["uv", "run", "--quiet", "toprope-author", "init", str(tmp_path)],
                       capture_output=True, text=True, timeout=60, env={**os.environ})
    assert r.returncode == 0
    Workspace(tmp_path)   # parses
    assert "local_only" in Path(tmp_path / "toprope.workspace.yaml").read_text()


def test_bad_values_and_config_are_authoring_errors(ws):
    _seed_example(ws)
    with pytest.raises(AuthoringError, match="must be an object"):
        ws.propose("scenarios.s1", "just text", "docs:docs/process.md#L7-L8")
    (ws.root / "toprope.workspace.yaml").write_text(yaml.safe_dump({**CONFIG, "event_store": "mongo:x"}))
    with pytest.raises(AuthoringError, match="event_store"):
        Workspace(ws.root).questions()
