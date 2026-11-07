import asyncio
import json
from pathlib import Path

import pytest
import yaml
from mcp import Client

from test_decl import schema_doc_domain
from toprope.workspace import AuthoringError, Workspace
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


def test_a_source_that_points_at_removed_files_is_stale(tmp_path):
    # The mistake #91 fixed: the switch-over removed files the Authoring workspace still read.
    cfg = {"domain": "d.domain.yaml", "sources": [
        {"id": "system", "kind": "repository", "path": "src", "globs": ["kernel/**", "authoring/**"]},
        {"id": "records", "kind": "records", "path": "docs", "globs": ["workflow.md", "authoring.md"]},
        {"id": "gone", "kind": "records", "path": "notes"},
        {"id": "link", "kind": "records", "url": "https://example.com/policy"},
    ]}
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(cfg))
    (tmp_path / "src" / "kernel").mkdir(parents=True)
    (tmp_path / "src" / "kernel" / "services.py").write_text("x = 1\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "workflow.md").write_text("# Workflow\n")
    assert Workspace(tmp_path).stale_sources() == [
        "source system: src/authoring/** matches no file",
        "source records: docs/authoring.md matches no file",
        "source gone: notes does not exist",
    ]


@pytest.mark.parametrize("workspace", ["toprope.authoring.workspace.yaml", "toprope.delivery.workspace.yaml"])
def test_the_self_domain_workspaces_point_at_files_that_exist(workspace):
    assert Workspace(Path(__file__).resolve().parent.parent / workspace).stale_sources() == []


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


def test_a_change_inside_a_confirmed_element_proposes_the_element_again(ws):
    """Otherwise an agent could rewrite a confirmed action's effects while it reads `confirmed`."""
    ws.propose("roles", ["approver"], "docs:docs/process.md#L4-L6")
    ws.propose("objects.Experiment", {"description": "A test.", "properties": {"ok": {"type": "boolean"}}},
               "docs:docs/process.md#L4-L6")
    ws.propose("actions.approve", {"description": "Approve.", "actor": ["approver"], "target": "Experiment",
                                   "effects": [{"set": {"target.ok": True}}]}, "docs:docs/process.md#L4-L6")
    ws.confirm(["actions.approve"], via="terminal", who="ana")
    assert ws.draft()["actions"]["approve"]["status"] == "confirmed"
    ws.propose("actions.approve.effects", [{"set": {"target.ok": False}}], "docs:docs/process.md#L7-L8")
    el = ws.draft()["actions"]["approve"]
    assert el["effects"] == [{"set": {"target.ok": False}}]
    assert el["status"] == "proposed" and el["source"]["ref"] == "docs:docs/process.md#L7-L8"


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
def test_questions_come_in_stage_bundles_starting_with_purpose(ws):
    _seed_example(ws)
    b = ws.questions(limit=50)
    assert b["stage"] == "purpose" and b["bundle_id"].startswith("bundle:purpose:")
    assert [q["kind"] for q in b["questions"]] == ["purpose"] * 3
    progress = {p["stage"]: p["status"] for p in b["progress"]}
    assert progress["sources"] == "done" and progress["cast"] == "done" and progress["purpose"] == "current"
    rows = ws.questions(limit=50, stage="transitions")["questions"]
    row = next(q for q in rows if q["kind"] == "row")
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
    calm = ws.questions(limit=50, attempts={}, stage="transitions")
    assert calm["stop"]["stop"] is True                         # nothing attempted, no effects
    hot = ws.questions(limit=50, attempts={"launch_experiment": 3}, stage="transitions")
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
    row = next(q for q in ws.questions(limit=50, stage="transitions")["questions"] if q["kind"] == "row")
    out = ws.answer(row["id"], "No. Once it has ended it never relaunches.",
                    [{"path": "transitions.Experiment.matrix.ended.launch_experiment",
                      "value": {"deny": "An ended experiment never relaunches."}}])
    assert out["ref"] == "interview:interview/log.jsonl#L1"
    cell = ws.draft()["transitions"]["Experiment"]["matrix"]["ended"]["launch_experiment"]
    assert cell["source"] == {"kind": "interview", "ref": "interview:interview/log.jsonl#L1",
                              "quote": "No. Once it has ended it never relaunches."}
    assert cell["status"] == "proposed"
    assert ws.chunks("interview")[0].ref == "interview:interview/log.jsonl#L1"   # citable afterwards
    assert not any(q["kind"] == "row" for q in ws.questions(limit=50, stage="transitions")["questions"])
    with pytest.raises(AuthoringError, match="owner's words"):
        ws.answer(row["id"], "  ", [])


def test_only_a_human_channel_confirms(ws):
    _seed_example(ws)
    ws.propose("objects.Readout", {"description": "Result."}, "docs:docs/process.md#L7-L8")
    with pytest.raises(AuthoringError, match="only a person"):
        ws.confirm(["objects.Readout"], via="agent")
    with pytest.raises(AuthoringError, match="not a drafted element"):
        ws.confirm(["roles"], via="terminal")
    ws.confirm(["objects.Readout"], via="terminal", who="owner")
    assert ws.draft()["objects"]["Readout"]["status"] == "confirmed"
    log = [json.loads(line) for line in ws.log_path.read_text().splitlines()]
    assert log[-1] == {**log[-1], "kind": "confirm", "paths": ["objects.Readout"], "via": "terminal"}


def test_check_runs_the_harness_on_the_draft(ws):
    _seed_example(ws)
    out = ws.check()
    assert out["parses"] and out["harness"]["ok"] and out["matrix"]["undecided"] == 1


# -- the authoring MCP ---------------------------------------------------------------------------
def _p(res):
    sc = res.structured_content
    return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc


def test_an_agent_drafts_through_the_generated_server_and_only_a_person_confirms(ws):
    """The authoring tools an agent uses are generated from the Authoring declaration (ADR-0037):
    it searches the sources (local-only ones are never served) and proposes elements with
    provenance; confirming is an action only a person takes."""
    from toprope.adapters.mcp import build_server
    from toprope.compose import assemble, load_composition
    from toprope.identity import Caller, StaticIdentity
    from toprope.kernel.services import LocalKernel
    from toprope.semantics import Actor, Grant
    from toprope.store import MemoryEventStore
    _seed_example(ws)
    owner = Actor("owen", "person", ("owner",))
    ids = StaticIdentity({"t-owen": Caller(owner), "t-bot": Caller(
        Actor("bot", "agent", ("owner",)), owner,
        Grant("drafting", frozenset({"search", "propose_element", "confirm_all_proposed"}), None))})
    c = load_composition(Path(__file__).resolve().parents[1] / "domains/toprope-self.composition.yaml")
    a = assemble(c, {n: MemoryEventStore() for n in c.domains}, ids,
                 services=LocalKernel(ws.root, workspace=ws))["authoring"]
    decl = str(ws.domain_path.relative_to(ws.root))
    for action, oid, params in (("open_draft", "d", {"domain_id": "example", "declaration": decl, "branch": "work"}),
                                ("add_source", "S-docs", {"kind": "records", "path": "docs"})):
        assert a.submit("t-owen", action, oid, params, action).ok
    who = type("As", (), {"token": "t-bot", "__call__": lambda self: self.token})()
    seen = {}

    async def go():
        async with Client(build_server(a, who)) as cl:
            def out(r):
                sc = r.structured_content
                return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
            found = out(await cl.call_tool("search", {"target_id": "d", "query": "approve",
                                                      "idempotency_key": "s1"}))
            assert found["status"] == "ok"
            refs = [e for e in a.history("d") if e.type == "DraftRecordSearch"][-1].payload["params"]["refs"]
            assert refs and not any(r.startswith("sessions:") for r in refs)          # local-only: never served
            ref = seen["ref"] = next(r for r in refs if r.startswith("docs:"))
            value = json.dumps({"description": "Result."})
            raw = await cl.call_tool("propose_element", {"new_id": "E-1", "path": "objects.Readout",
                                                           "origin": "S-docs", "cites": ref, "value": value,
                                                           "idempotency_key": "p1"})
            r = out(raw)
            assert r and r["status"] == "ok", raw
            denied = out(await cl.call_tool("confirm_all_proposed", {"target_id": "d", "idempotency_key": "c1"}))
            assert denied["status"] == "denied" and "Only a person" in denied["reason"]
    asyncio.run(go())
    assert ws.draft()["objects"]["Readout"]["status"] == "proposed"
    assert ws.draft()["objects"]["Readout"]["source"]["ref"] == seen["ref"]
    assert a.submit("t-owen", "confirm_all_proposed", "d", {}, "c2").ok
    assert ws.draft()["objects"]["Readout"]["status"] == "confirmed"
    entry = json.loads(ws.log_path.read_text().splitlines()[-1])
    assert entry["via"] == "kernel" and entry["who"] == "owen" and "objects.Readout" in entry["paths"]


def test_bad_values_and_config_are_authoring_errors(ws):
    _seed_example(ws)
    with pytest.raises(AuthoringError, match="must be an object"):
        ws.propose("scenarios.s1", "just text", "docs:docs/process.md#L7-L8")
    (ws.root / "toprope.workspace.yaml").write_text(yaml.safe_dump({**CONFIG, "event_store": "mongo:x"}))
    with pytest.raises(AuthoringError, match="event_store"):
        Workspace(ws.root).questions()


def test_a_workspace_may_be_named_by_its_file(tmp_path):
    """Several domains' workspaces can share one directory (the self domains share the repo)."""
    from toprope.workspace import Workspace
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\nrules\n")
    for name in ("one", "two"):
        (tmp_path / f"toprope.{name}.workspace.yaml").write_text(yaml.safe_dump({
            "domain": f"domains/{name}.domain.yaml", "interview_log": f"interview/{name}/log.jsonl",
            "sources": [{"id": "docs", "kind": "records", "path": "docs"}]}))
    one, two = Workspace(tmp_path / "toprope.one.workspace.yaml"), Workspace(tmp_path / "toprope.two.workspace.yaml")
    assert one.root == two.root == tmp_path.resolve()
    assert one.domain_path.name == "one.domain.yaml" and two.log_path.parts[-2] == "two"
    assert one.chunks("docs")


def test_a_terminal_confirmation_records_the_git_identity(tmp_path):
    """Who confirmed comes from the terminal's git identity, without anyone typing it."""
    import json
    import subprocess
    from toprope.workspace import Workspace
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Ana Owner"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "ana@example.org"], check=True)
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(
        {"domain": "d.domain.yaml", "sources": [{"id": "docs", "kind": "records", "path": "docs"}]}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\nrules\n")
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    ws = Workspace(tmp_path)
    ws.propose("actions.approve_experiment", ws.draft()["actions"]["approve_experiment"], "docs:docs/a.md#L1-L2")
    ws.confirm(["actions.approve_experiment"], via="terminal")
    entry = json.loads(ws.log_path.read_text().splitlines()[-1])
    assert entry["who"] == "Ana Owner <ana@example.org>"
    ws.confirm(["actions.approve_experiment"], via="terminal", who="eli")              # an explicit name wins
    assert json.loads(ws.log_path.read_text().splitlines()[-1])["who"] == "eli"



def test_the_terminal_is_named_as_the_identity_file_names_it(tmp_path):
    """#85: `Workspace.identity` used git's `user.name`, the git identity adapter the file's name,
    so one person had two names in the logs. The file's name wins when it lists the email."""
    import subprocess
    from toprope.workspace import Workspace
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "ana-laptop"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "ana@example.org"], check=True)
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    ws = Workspace(tmp_path)
    assert ws.identity() == "ana-laptop <ana@example.org>"                  # no identity file: git's name
    (tmp_path / "toprope.identity.yaml").write_text(yaml.safe_dump(
        {"people": {"ana@example.org": {"name": "Ana Kim", "roles": ["owner"]}}}))
    assert ws.identity() == "Ana Kim <ana@example.org>"                     # the file's name, as GitIdentity


def test_the_removed_channels_are_refused(ws):
    """#89: the CLI confirm and the MCP elicitation are gone; a person confirms at the terminal
    or through a declared action."""
    _seed_example(ws)
    ws.propose("objects.Readout", {"description": "Result."}, "docs:docs/process.md#L7-L8")
    for old in ("cli", "elicitation"):
        with pytest.raises(AuthoringError, match="only a person"):
            ws.confirm(["objects.Readout"], via=old, who="owner")


def test_the_git_identity_reads_git_once_per_command(tmp_path, monkeypatch):
    """#85: a command resolved its caller twice and read `git config` each time."""
    import toprope.identity.git as g
    calls = []
    monkeypatch.setattr(g, "git_email", lambda root: calls.append(root) or "ana@example.org")
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump({"people": {"ana@example.org": {"roles": ["owner"]}}}))
    ident = g.GitIdentity(tmp_path / "ids.yaml", tmp_path, once=True)
    assert ident.resolve() is not None and ident.resolve() is not None
    ident.explain()
    assert len(calls) == 1
    live = g.GitIdentity(tmp_path / "ids.yaml", tmp_path)                 # a long-lived process: each time
    live.resolve(), live.resolve()
    assert len(calls) == 3
    from toprope.adapters.cli import _identity
    monkeypatch.chdir(tmp_path)
    assert _identity("git:ids.yaml").once is True                          # toprope-run: one command

def test_a_handoff_is_an_element_to_confirm(tmp_path):
    """A handoff is a decision about what crosses into another domain: drafted, then confirmed."""
    from toprope.workspace import Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(
        {"domain": "d.domain.yaml", "sources": [{"id": "docs", "kind": "records", "path": "docs"}]}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\nhand approved experiments to delivery\n")
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    ws = Workspace(tmp_path)
    ws.propose("handoffs.deliver", {"when": {"action": "approve_experiment"},
                                    "to": {"domain": "delivery", "interface": "1.x", "action": "request_delivery"},
                                    "params": {}, "target": "target.id"}, "docs:docs/a.md#L1-L2")
    assert "handoffs.deliver" in ws._proposed(ws.draft())
    ws.confirm(["handoffs.deliver"], via="terminal", who="ana")
    assert ws.draft()["handoffs"]["deliver"]["status"] == "confirmed"


def test_the_kernel_confirms_every_proposed_element_at_once(tmp_path):
    from toprope.kernel.services import LocalKernel
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(
        {"domain": "d.domain.yaml", "sources": [{"id": "docs", "kind": "records", "path": "docs"}]}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\nrules\n")
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    ws = Workspace(tmp_path)
    for a in ("approve_experiment", "launch_experiment"):
        ws.propose(f"actions.{a}", ws.draft()["actions"][a], "docs:docs/a.md#L1-L2")
    k = LocalKernel(tmp_path, workspace=ws)
    ana = {"id": "ana", "kind": "person"}
    proposed = ws._proposed(ws.draft())
    assert {"actions.approve_experiment", "actions.launch_experiment"} <= set(proposed)
    agent = k.call("confirm_element", {"paths": "all", "approver": "ana"}, caller={"id": "bot", "kind": "agent"})
    assert not agent["ok"] and ws._proposed(ws.draft()) == proposed                 # only the person, as themself
    out = k.call("confirm_element", {"paths": "all", "approver": "ana"}, caller=ana)
    assert out["ok"] and out["confirmed"] == proposed and ws._proposed(ws.draft()) == []
    entry = json.loads(ws.log_path.read_text().splitlines()[-1])
    assert entry["paths"] == proposed and entry["who"] == "ana" and entry["via"] == "kernel"
    again = k.call("confirm_element", {"paths": "all", "approver": "ana"}, caller=ana)
    assert not again["ok"] and "nothing to confirm" in again["error"]




def test_a_committed_domain_refuses_a_proposal_that_breaks_its_declaration(tmp_path):
    # #124: an action proposed before the reply it names made the working copy invalid, and the
    # generated tools then refused to load it at all, so nothing could undo the proposal.
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(
        {"domain": "d.domain.yaml", "sources": [{"id": "docs", "kind": "records", "path": "docs"}]}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\nrules\n")
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    ws = Workspace(tmp_path)
    ws.commit()
    cite = {"description": "Cite.", "actor": ["pm"], "target": "Experiment",
            "effects": [{"call": "validate", "with": {"declaration": "target.name"}, "reply": "record_it"}]}
    before = ws.domain_path.read_text()
    with pytest.raises(AuthoringError, match="unknown-reply"):
        ws.propose("actions.cite", cite, "docs:docs/a.md#L1-L2")
    assert ws.domain_path.read_text() == before                          # nothing written
    ws.propose("actions.record_it", {"description": "Record.", "actor": ["external:kernel"],
                                     "target": "Experiment"}, "docs:docs/a.md#L1-L2")
    out = ws.propose("actions.cite", cite, "docs:docs/a.md#L1-L2")       # in dependency order
    assert not [i for i in out["issues"] if i["code"] == "unknown-reply"]


def test_a_scenario_is_an_element_and_a_fixture_change_is_logged(ws):
    """#86, #147: a proposed scenario was written without provenance, so no person confirmed it.
    A scenario is an element now; fixtures and the glossary, which carry none, are logged."""
    from toprope.decl.provenance import proposed_elements
    _seed_example(ws)
    sc = {"id": "approve-needs-a-guardrail", "given": {"from_world": "E-bare"},
          "steps": [{"actor": {"role": "approver"}, "do": "approve_experiment", "target": "E-bare",
                     "expect": {"denied_by": "has-guardrails"}}]}
    out = ws.propose(f"scenarios.{sc['id']}", sc, "docs:docs/process.md#L4-L6")
    assert out["marked"] is True
    (added,) = [s for s in ws.draft()["scenarios"] if s["id"] == sc["id"]]
    assert added["status"] == "proposed" and added["source"]["ref"] == "docs:docs/process.md#L4-L6"
    assert f"scenarios.{sc['id']}" in proposed_elements(ws.draft())
    ws.confirm([f"scenarios.{sc['id']}"], via="kernel", who="ana")
    assert f"scenarios.{sc['id']}" not in proposed_elements(ws.draft())
    fx = ws.draft()["world"]["fixtures"]
    assert ws.propose("world.fixtures", fx, "docs:docs/process.md#L4-L6")["marked"] is False
    last = json.loads(ws.log_path.read_text().splitlines()[-1])
    assert last["kind"] == "unmarked-proposal" and last["path"] == "world.fixtures"
