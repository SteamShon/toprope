"""An import goes through theme 1's change loop, and a server's tools reach an enforced binding
(ADR-0049 A1 and C1, ADR-0051, ADR-0052 §7). Review of theme 4, 2026-11-10."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from toprope import kernel
from toprope.importers.cli import main as import_main

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples/import"
API, SQL = EX / "orders.openapi.yaml", EX / "orders.sql"
ME = "steamshon <steamshon@apache.org>"
RUN = [sys.executable, "-c", "from toprope.adapters.cli import main; main()", "--identity", "static:ids.yaml"]
PROXY = [sys.executable, "-c", "from toprope.proxy.cli import main; main()"]


@pytest.fixture(autouse=True)
def no_upstream_services():
    yield
    kernel.UPSTREAM_SERVICES.clear()


def test_a_patch_cites_chunks_of_the_source_it_registers_in_the_workspace(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    shutil.copy(API, tmp_path / "orders.openapi.yaml")
    ws = tmp_path / "shop.workspace.yaml"
    import_main(["openapi", "orders.openapi.yaml", "--domain", "shop", "--patch", "p.yaml", "--workspace", str(ws)])
    text = capsys.readouterr().out
    assert "toprope-run open_draft shop --domain-id shop --declaration shop.domain.yaml" in text
    assert "toprope-change \"import from orders.openapi.yaml\" --patch p.yaml" in text
    cfg = yaml.safe_load(ws.read_text())
    assert cfg["domain"] == "shop.domain.yaml"
    assert cfg["sources"] == [{"id": "shop-openapi", "kind": "repository", "path": "orders.openapi.yaml"}]  # in place
    items = yaml.safe_load((tmp_path / "p.yaml").read_text())
    from toprope.adapters.cli.change import read_patch
    assert read_patch(tmp_path / "p.yaml") == items                                  # the format toprope-change takes
    assert [i["path"] for i in items][:4] == ["roles", "objects.Order", "actions.create_order", "actions.refund_order"]
    from toprope.workspace import Workspace
    w = Workspace(ws)
    for it in items:
        assert w.resolve_ref(it["cites"])[0] == it["cites"] and it["origin"] == "S-shop-openapi"
    refund = next(i for i in items if i["path"] == "actions.refund_order")
    assert refund["place"] == "orders.openapi.yaml#/paths/~1orders~1{id}~1refund/post"
    assert "source" not in refund["value"] and "status" not in refund["value"]       # propose_element adds those


def test_a_source_outside_the_workspace_is_kept_as_a_snapshot_and_comments_survive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "shop.workspace.yaml"
    ws.write_text("# our workspace\ndomain: shop.domain.yaml\nsources:\n    - id: docs   # the handbook\n"
                  "      kind: records\n      path: docs\n\nusage_log: used.jsonl\n")
    import_main(["sql", str(SQL), "--patch", "p.yaml", "--workspace", str(ws)])
    text = ws.read_text()
    assert text.startswith("# our workspace") and "# the handbook" in text
    cfg = yaml.safe_load(text)
    assert [s["id"] for s in cfg["sources"]] == ["docs", "shop-sql"] and cfg["usage_log"] == "used.jsonl"
    snap = tmp_path / cfg["sources"][1]["path"]
    assert snap.read_bytes() == SQL.read_bytes() and snap.is_relative_to(tmp_path / ".toprope/imports")
    (tmp_path / "p.yaml").unlink()
    import_main(["sql", str(SQL), "--patch", "p.yaml", "--workspace", str(ws)])     # the same source again: kept
    assert [s["id"] for s in yaml.safe_load(ws.read_text())["sources"]] == ["docs", "shop-sql"]
    (tmp_path / "p.yaml").unlink()
    with pytest.raises(SystemExit, match="already has a source 'shop-sql'.*Fix: give --source-id a new id"):
        import_main(["openapi", str(API), "--patch", "p.yaml", "--workspace", str(ws), "--source-id", "shop-sql"])


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A copy of the repository with the self domains' approved declarations and empty logs, as
    test_toprope_change makes it."""
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    for f in filter(None, files):
        src, dst = ROOT / f.decode(), tmp_path / f.decode()
        if "/events/" in f.decode() or not src.is_file():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    from toprope.commits import CommitStore
    approved = CommitStore(ROOT / ".toprope" / "commits")
    for d in ("authoring", "delivery"):
        approved.export(d, approved.main(d).id, tmp_path / f"domains/{d}/{d}.domain.yaml")
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump({
        "t-owen": {"id": ME, "roles": ["owner", "approver"]},
        "t-bot": {"id": "bot <bot@example.com>", "kind": "agent", "roles": ["owner"],
                  "on_behalf_of": {"id": ME, "roles": ["owner", "approver"]},
                  "grant": {"id": "drafting", "actions": ["propose_element", "add_source", "ask_question"]}}}))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(cmd, token, ok=True):
    r = subprocess.run(cmd, capture_output=True, text=True, check=False, env={**os.environ, "TOPROPE_TOKEN": token})
    assert (r.returncode == 0) == ok, r.stderr + r.stdout
    return r


def test_a_servers_tools_reach_an_enforced_binding_through_the_change_loop(repo):
    """payments_server.py → a drafted declaration and binding → proposed through toprope-change by
    an agent → confirmed by the person with the commands they run → the proxy's start check passes.
    No YAML is written by hand."""
    server = f"{sys.executable} examples/proxy/payments_server.py"
    ws = "toprope.payments.workspace.yaml"
    imp = [sys.executable, "-c", "from toprope.importers.cli import main; main()"]
    out = run([*imp, "mcp", server, "--domain", "payments", "--patch", "import.yaml", "--workspace", ws,
               "--binding-out", "payments.binding.yaml", "--questions", "q.yaml"], "t-bot").stdout
    nxt = [ln.strip() for ln in out.splitlines() if ln.startswith("  toprope-")]
    assert nxt[0] == "toprope-run open_draft payments --domain-id payments --declaration payments.domain.yaml --branch work"
    assert nxt[1].startswith("toprope-run add_source S-payments-mcp --kind repository --path .toprope/imports/")
    base = ["--workspace", ws]
    run([*RUN, *base, *nxt[0].split()[1:]], "t-owen")                     # the person opens the draft
    run([*RUN, *base, *nxt[1].split()[1:]], "t-bot")                      # the agent names the source
    from toprope.adapters.cli import change
    r = run([sys.executable, "-c", "from toprope.adapters.cli.change import main; main()",
             "import from the payments server", "--patch", "import.yaml", "--workspace", ws, "--draft", "payments",
             "--run-args", "--identity static:ids.yaml"], "t-bot")        # the agent proposes, checks, requests
    result = json.loads(r.stdout[r.stdout.index("{\n"):])
    assert {"objects.Order", "actions.refund_order", "actions.record_refund_order"} <= set(result["proposed"])
    assert result["checked"].startswith("passes") and (repo / result["request"]).is_file()
    assert "+ actions.refund_order" in r.stdout                            # the one diff the person confirms
    assert change.read_patch(repo / "import.yaml")
    decl = yaml.safe_load((repo / "payments.domain.yaml").read_text())
    assert decl["actions"]["refund_order"]["source"]["ref"].startswith("payments-mcp:.toprope/imports/")
    assert decl["actions"]["refund_order"]["status"] == "proposed"
    check = [*PROXY, "--check", "--domain", "payments.domain.yaml", "--binding", "payments.binding.yaml"]
    refused = run(check, "t-owen", ok=False).stderr
    assert "the binding is a draft no person has confirmed" in refused and "no person has confirmed" in refused
    confirm = [*PROXY, "--confirm-binding", "--domain", "payments.domain.yaml", "--binding", "payments.binding.yaml",
               "--identity", "static:ids.yaml"]
    assert "only a person confirms a binding" in run(confirm, "t-bot", ok=False).stderr
    req = yaml.safe_load((repo / result["request"]).read_text())
    first = req["steps"][0]["run"]                                         # the request's confirm step, as the person
    assert first["action"] == "confirm_all_proposed"
    run([*RUN, *base, first["action"], first["target"]], "t-owen")
    run(confirm, "t-owen")
    assert "ok: payments.binding.yaml, the server's tools and payments.domain.yaml agree; 1 tool(s) gated" in \
        run(check, "t-owen").stdout
    binding = yaml.safe_load((repo / "payments.binding.yaml").read_text())
    assert binding["status"] == "confirmed" and binding["confirmed_by"] == ME
    q = yaml.safe_load((repo / "q.yaml").read_text())
    ask = next(x for x in q["questions"] if x["kind"] == "actor")
    run([*RUN, *base, "ask_question", ask["id"], "--stage", "import", "--text", ask["text"]], "t-bot")  # into the interview
