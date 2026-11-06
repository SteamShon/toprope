"""The interview as kernel services (ADR-0037): any domain's authoring can declare it."""
import json

import yaml

from test_decl import schema_doc_domain
from toprope.kernel.services import LocalKernel
from toprope.workspace import Workspace


def kernel(tmp_path):
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(
        {"domain": "d.domain.yaml", "sources": [{"id": "docs", "kind": "records", "path": "docs"}]}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "rules.md").write_text("# Rules\nA launch needs an approver.\n")
    raw = schema_doc_domain()
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    ws = Workspace(tmp_path)
    return LocalKernel(tmp_path, workspace=ws), ws


ANA = {"id": "ana", "kind": "person"}


def test_search_propose_answer_confirm_and_skip_through_the_kernel(tmp_path):
    k, ws = kernel(tmp_path)
    (ref,) = k.call("search_sources", {"query": "launch needs"})["refs"]
    raw = ws.draft()["actions"]["launch_experiment"]
    out = k.call("propose_element", {"path": "actions.launch_experiment", "value": json.dumps(raw), "source": ref})
    assert out["ok"] and ws.draft()["actions"]["launch_experiment"]["status"] == "proposed"
    bad = k.call("propose_element", {"path": "actions.launch_experiment", "value": json.dumps(raw),
                                     "source": "docs:docs/nope.md#L1-L2"})
    assert not bad["ok"]                                                    # no real chunk: refused
    q = k.call("stage_questions", {})
    assert q["ok"] and q["stage"] and q["questions"]
    a = k.call("record_answer", {"question": "Who launches?", "answer": "Engineers do.",
                                 "decisions": json.dumps([{"path": "actions.launch_experiment", "value": raw}])})
    assert a["ok"] and a["ref"].endswith("#L1")                             # the first line of the log
    refused = k.call("confirm_element", {"paths": "all", "approver": "ana"},
                     caller={"id": "bot", "kind": "agent"})
    assert not refused["ok"] and ws._proposed(ws.draft())                  # only that person confirms
    done = k.call("confirm_element", {"paths": "all", "approver": "ana"}, caller=ANA)
    assert done["ok"] and "actions.launch_experiment" in done["confirmed"] and ws._proposed(ws.draft()) == []
    entry = json.loads(ws.log_path.read_text().splitlines()[-1])
    assert entry["kind"] == "confirm" and entry["via"] == "kernel" and entry["who"] == "ana"
    assert k.call("skip_stage", {"stage": "handoffs", "reason": "nothing crosses"})["skipped"]


def test_a_declaration_can_call_the_interview_services():
    from toprope.decl import Domain, validate_domain
    raw = schema_doc_domain()
    raw["actions"]["confirm_all"] = {"description": "Confirm what is drafted.", "actor": ["approver"], "target": "Experiment",
                                     "requires": "human", "effects": [{"call": "confirm_element",
                                     "with": {"paths": "'all'", "approver": "actor.id"}, "reply": "record_confirmed"}]}
    raw["actions"]["record_confirmed"] = {"description": "Record it.", "actor": ["external:kernel"], "target": "Experiment",
                                         "params": {"confirmed": {"type": "string", "many": True}}}
    for row in raw["transitions"]["Experiment"]["matrix"].values():
        row["confirm_all"] = "n/a"
        row["record_confirmed"] = "n/a"
    raw["transitions"]["Experiment"]["matrix"]["draft"].update(confirm_all="draft", record_confirmed="draft")
    assert [i for i in validate_domain(Domain.model_validate(raw)) if i.severity == "error"] == []
