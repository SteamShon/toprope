"""Post-deploy probes (docs/experiments/M1-self-compile.md, "Deploy and post-deploy discovery";
ADR-0040 §6).

After every change, each arm runs the eight frozen probes (P01–P08). A probe agent is the same
model, given the probe's task and a starting state, and the same generic tools in every arm:

  message_person   the only way to reach the owner, who is not at their desk
  read_source      read a source by its id or address
  commit_log, commit_diff, deployed
                   the commit history and what the environment runs (kernel reads)

Then each arm's way to the domain's objects:

  NL, structured   list/get/create/update objects in the state, as JSON, with the arm's text
                   (SKILL.md, or the YAML) as the rules to follow
  Toprope          the generated MCP tools of the domains as deployed, over the same state

The starting states are built once per run, from the approved self domains, by taking their
actions as the owner on a small `library` domain (`world/library.domain.yaml`): so they are
the same for every arm and every change. The Toprope arm's probe opens them with the tools as
deployed; when that fails (a change broke reading the existing state), the probe records it.

The probe agent gets the task and the starting state, never what the probe checks (`must`,
`must_not`): those are for the grader.
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from .agent import Tool, ToolError, Transcript
from .arms import prompt
from .toprope_arm import DOMAINS, Sandbox

WORLD = Path(__file__).parent / "world"
OWNER = "owner <owner@library.invalid>"
TOKENS = {"owner": "t-owner", "agent": "t-agent"}
RULES_URL = "https://lending-rules.library.invalid/policy"     # never resolves: P03's unreadable source
NOTES = "Lending notes from the owner.\n\nEvery lent book has a borrower. A member may renew a book once.\n"
COMPOSITION = "toolchain/toprope-self.composition.yaml"
PROBES = [f"P0{i}" for i in range(1, 9)]


def _grant(repo: Path) -> dict[str, Any]:
    """The grant the repository gives its own agent (toprope.identity.yaml): the probe agent works
    under the same one."""
    ids = yaml.safe_load((repo / "toprope.identity.yaml").read_text())
    (agent,) = ids["agents"].values()
    return agent["grant"]


def _ids(repo: Path) -> dict[str, Any]:
    person = {"id": OWNER, "roles": ["owner", "approver"]}
    return {TOKENS["owner"]: {**person, "kind": "person"},
            TOKENS["agent"]: {"id": "agent <agent@library.invalid>", "kind": "agent", "roles": ["owner", "approver"],
                              "on_behalf_of": person, "grant": _grant(repo)}}


def _workspace() -> dict[str, Any]:
    return {"domain": "library/library.domain.yaml", "interview_log": "library/interview.jsonl",
            "usage_log": "library/sources-used.jsonl",
            "sources": [{"id": "interview", "kind": "interview-log", "path": "library/interview.jsonl"},
                        {"id": "notes", "kind": "records", "path": "notes"},
                        {"id": "rules", "kind": "records", "url": RULES_URL}]}


CREATES = {"open_draft": "Draft", "add_source": "Source", "ask_question": "Question",
           "answer_question": "Answer", "propose_element": "Element"}


class World:
    """One probe's starting state: a kernel root with the toolchain and the `library` domain."""

    def __init__(self, root: Path):
        self.root = root
        self.sb = Sandbox(root, TOKENS, reader="owner")
        self.ids: list[tuple[str, str, str]] = []     # (member, id, type) of every object made

    def act(self, member: str, *args: str) -> dict[str, Any]:
        out = self.sb.ok("owner", member, "library", *args)
        if args[0] in CREATES:
            self.ids.append((member, args[1], CREATES[args[0]]))
        for t in out.get("then", []):
            if t.get("handoff") and t.get("object"):
                self.ids.append(("delivery", t["object"], "DeliveryRequest"))
            elif args[0] == "commit_draft" and t.get("object"):
                self.ids.append((member, t["object"], "Commit"))
        return out

    def made(self, out: dict[str, Any]) -> str:
        return next(t["object"] for t in out.get("then", []) if t.get("object"))

    def get(self, member: str, oid: str) -> Any:
        return self.sb.get(member, "library", oid)


def _new_world(repo: Path, root: Path, toolchain: Path) -> World:
    (root / "toolchain").mkdir(parents=True)
    shutil.copy(toolchain / "toprope-self.composition.yaml", root / COMPOSITION)
    for d in DOMAINS:
        (root / "toolchain" / d).mkdir()
        shutil.copy(toolchain / d / f"{d}.domain.yaml", root / "toolchain" / d / f"{d}.domain.yaml")
    (root / "library").mkdir()
    shutil.copy(WORLD / "library.domain.yaml", root / "library/library.domain.yaml")
    (root / "library/interview.jsonl").write_text("")
    (root / "notes").mkdir()
    (root / "notes/lending.md").write_text(NOTES)
    (root / "toprope.library.workspace.yaml").write_text(yaml.safe_dump(_workspace(), sort_keys=False))
    (root / "ids.yaml").write_text(yaml.safe_dump(_ids(repo), sort_keys=False))
    return World(root)


RENEW = {"description": "Renew a lent book once.", "actor": ["librarian"], "target": "Book", "effects": []}
INSPECT = {"description": "Look a book over for damage.", "actor": ["librarian"], "target": "Book", "effects": []}


def _base(w: World) -> dict[str, Any]:
    """A drafted, approved and deployed first commit of `library`."""
    w.act("authoring", "open_draft", "library", "--domain-id", "library", "--declaration",
          "library/library.domain.yaml", "--branch", "work")
    w.act("authoring", "add_source", "S-notes", "--kind", "records", "--path", "notes")
    w.act("authoring", "ask_question", "Q-1", "--stage", "actions", "--text", "What must a lent book have?")
    w.act("authoring", "answer_question", "A-1", "--question", "Q-1", "--words", NOTES.split("\n\n")[1].strip(),
          "--decisions", "[]")
    c1 = _commit(w)
    _approve(w, c1)
    r1 = w.made(w.act("authoring", "deliver", c1, "--environment", "local"))
    for action in ("preview", "deploy"):
        w.act("delivery", action, r1)
    w.act("delivery", "verify", r1, "--verified", "true")
    return {"draft": "library", "deployed": c1}


def _propose(w: World, eid: str, path: str, value: Any) -> None:
    w.act("authoring", "propose_element", eid, "--path", path, "--origin", "S-notes",
          "--cites", w.get("authoring", "A-1")["ref"], "--value", json.dumps(value))


def _commit(w: World) -> str:
    w.sb.run("owner", "authoring", "library", "confirm_all_proposed", "library")    # nothing proposed: refused
    c = w.made(w.act("authoring", "commit_draft", "library"))
    w.act("authoring", "check_commit", c)
    return c


def _approve(w: World, c: str) -> None:
    w.act("authoring", "approve_commit", c)


def _p01(w):
    s = _base(w)
    _propose(w, "E-renew", "actions.renew", RENEW)
    _propose(w, "E-inspect", "actions.inspect", INSPECT)
    return {**s, "proposed": ["E-renew", "E-inspect"]}


def _p02(w):
    s = _base(w)
    _propose(w, "E-renew", "actions.renew", RENEW)
    reviewed = _commit(w)
    _propose(w, "E-inspect", "actions.inspect", INSPECT)
    newer = _commit(w)
    return {**s, "reviewed_by_owner": reviewed, "newest": newer}


def _p03(w):
    s = _base(w)
    w.act("authoring", "add_source", "rules", "--kind", "records", "--path", RULES_URL)
    return {**s, "source": "rules", "address": RULES_URL}


def _p04(w):
    s = _base(w)
    w.act("authoring", "next_questions", "library")
    return s


def _p05(w):
    s = _base(w)
    _propose(w, "E-renew", "actions.renew", RENEW)
    return {**s, "unapproved": _commit(w)}


def _approved_pair(w):
    _propose(w, "E-renew", "actions.renew", RENEW)
    c2 = _commit(w)
    _approve(w, c2)
    _propose(w, "E-inspect", "actions.inspect", INSPECT)
    c3 = _commit(w)
    _approve(w, c3)
    return c2, c3


def _p06(w):
    s = _base(w)
    c2, c3 = _approved_pair(w)
    return {**s, "approved_since": [c2, c3]}


def _p07(w):
    s = _base(w)
    _propose(w, "E-renew", "actions.renew", RENEW)
    c2 = _commit(w)
    _approve(w, c2)
    return {**s, "approved": c2}


def _p08(w):
    s = _base(w)
    c2, c3 = _approved_pair(w)
    r2 = w.made(w.act("authoring", "deliver", c2, "--environment", "local"))
    w.act("delivery", "preview", r2)
    w.sb.run("owner", "delivery", "library", "deploy", r2)              # superseded by c3: a floor refuses
    request = w.get("delivery", r2)
    return {**s, "request": r2, "deployed": request.get("deployed"), "refusal": request.get("refusal"),
            "newest_approved": c3}


SETUPS = {"P01": _p01, "P02": _p02, "P03": _p03, "P04": _p04, "P05": _p05, "P06": _p06, "P07": _p07, "P08": _p08}


def _export(w: World) -> dict[str, Any]:
    """The state as plain data, for the arms that have no domain tools."""
    objects: dict[str, Any] = {}
    for member, oid, type_ in w.ids:
        if oid not in objects and (obj := w.get(member, oid)) and isinstance(obj, dict) and obj.get("id"):
            obj.pop("status", None)                        # the command's outcome, not the object's
            objects[oid] = {"type": type_, **obj}
    return {"objects": objects}


def build_worlds(repo: Path, toolchain: Path, out: Path) -> dict[str, Any]:
    """Each probe's starting state, built once by the owner with the tools in `toolchain`."""
    if out.exists():
        raise FileExistsError(out)
    made = {}
    for pid, setup in SETUPS.items():
        w = _new_world(repo, out / pid, toolchain)
        situation = setup(w)
        (w.root / "situation.json").write_text(json.dumps(situation, indent=2) + "\n")
        (w.root / "state.json").write_text(json.dumps(_export(w), indent=2, ensure_ascii=False, default=str) + "\n")
        made[pid] = situation
    return made


# -- the probe agent's tools ----------------------------------------------------------------------

def generic_tools(root: Path, with_objects: bool) -> list[Tool]:
    """What every arm's probe agent has, plus, for a text arm, the objects as JSON."""
    outbox = root / "outbox.jsonl"
    state_path = root / "state.json"

    def message_person(text: str, choices: list[str] | None = None) -> str:
        with outbox.open("a") as f:
            f.write(json.dumps({"to": OWNER, "text": text, "choices": choices or []}, ensure_ascii=False) + "\n")
        return "Sent to the owner. They are not at their desk and have not answered yet."

    def read_source(source: str) -> str:
        if source in ("rules", RULES_URL):
            raise ToolError(f"cannot read {RULES_URL}: the address does not resolve from here")
        if source in ("notes", "S-notes", "notes/lending.md"):
            return (root / "notes/lending.md").read_text()
        raise ToolError(f"no source {source!r}")

    def store():
        from toprope.commits import CommitStore
        return CommitStore(root / ".toprope/commits")

    def commit_log() -> list[dict[str, Any]]:
        st = store()
        approved = {a["commit"] for a in st.approvals("library")}
        return [{"id": c.id, "parents": c.parents, "branch": c.branch, "author": c.author, "approved": c.id in approved}
                for c in st.log("library")]

    def commit_diff(from_commit: str, to_commit: str) -> dict[str, Any]:
        try:
            return store().diff("library", from_commit or None, to_commit)
        except Exception as e:                                   # noqa: BLE001 - shown to the agent
            raise ToolError(str(e)) from None

    def deployed() -> dict[str, Any]:
        from toprope.deploy import LocalEnvironment
        env = LocalEnvironment(root / ".toprope/env-library")
        return {"current": env.current(), "history": env.history()[-10:]}

    s, obj = {"type": "string"}, {"type": "object"}
    tools = [
        Tool("message_person", "Send the owner a message, optionally with choices to pick from.",
             {"type": "object", "properties": {"text": s, "choices": {"type": "array", "items": s}},
              "required": ["text"]}, message_person),
        Tool("read_source", "Read a source by its id or address.",
             {"type": "object", "properties": {"source": s}, "required": ["source"]}, read_source),
        Tool("commit_log", "The library domain's commits, newest last, and which are approved.",
             {"type": "object", "properties": {}}, commit_log),
        Tool("commit_diff", "What changed between two commits.",
             {"type": "object", "properties": {"from_commit": s, "to_commit": s}, "required": ["from_commit", "to_commit"]},
             commit_diff),
        Tool("deployed", "What the environment runs now, and its recent history.",
             {"type": "object", "properties": {}}, deployed),
    ]
    if not with_objects:
        return tools

    def load() -> dict[str, Any]:
        return json.loads(state_path.read_text())

    def save(st: dict[str, Any]) -> None:
        state_path.write_text(json.dumps(st, indent=2, ensure_ascii=False))

    def list_objects(type: str = "") -> list[dict[str, Any]]:
        return [{"id": k, "type": v.get("type")} for k, v in load()["objects"].items()
                if not type or v.get("type") == type]

    def get_object(id: str) -> dict[str, Any]:
        o = load()["objects"].get(id)
        if o is None:
            raise ToolError(f"no object {id!r}")
        return o

    def create_object(type: str, id: str, fields: dict[str, Any]) -> str:
        st = load()
        if id in st["objects"]:
            raise ToolError(f"{id!r} exists")
        st["objects"][id] = {"type": type, "id": id, **fields}
        save(st)
        return f"created {id}"

    def update_object(id: str, fields: dict[str, Any]) -> str:
        st = load()
        if id not in st["objects"]:
            raise ToolError(f"no object {id!r}")
        st["objects"][id].update(fields)
        save(st)
        return f"updated {id}"

    return tools + [
        Tool("list_objects", "List the objects in the state, optionally of one type.",
             {"type": "object", "properties": {"type": s}}, list_objects),
        Tool("get_object", "Read one object.", {"type": "object", "properties": {"id": s}, "required": ["id"]},
             get_object),
        Tool("create_object", "Create an object.",
             {"type": "object", "properties": {"type": s, "id": s, "fields": obj}, "required": ["type", "id", "fields"]},
             create_object),
        Tool("update_object", "Change fields of an object.",
             {"type": "object", "properties": {"id": s, "fields": obj}, "required": ["id", "fields"]}, update_object),
    ]


def probe_tools(root: Path, ctx: dict[str, Any]) -> list[Tool]:
    return generic_tools(root, with_objects=bool(ctx.get("objects")))


# -- running the probes ---------------------------------------------------------------------------

def load_probes(instruments: Path) -> list[dict[str, Any]]:
    return yaml.safe_load((instruments / "probe-suite.yaml").read_text())["probes"]


def _user(p: dict[str, Any], situation: dict[str, Any]) -> str:
    return (f"Situation: {p['starting_state']}\nDetails: {json.dumps(situation)}\n\n"
            f"Task: {p['task']}")


def servers(root: Path) -> dict[str, Any]:
    """The generated MCP servers of the deployed domains, over a probe world, as the agent."""
    exe = Path(sys.executable).parent / "toprope-server"
    if not exe.exists():
        raise RuntimeError(f"toprope-server is not installed next to this Python ({sys.executable})")
    exe = str(exe)
    return {m: {"command": exe, "args": ["--composition", str(root / COMPOSITION), "--working-copy", "--member", m,
                                         "--kernel-root",
                                         str(root), "--workspace", str(root / "toprope.library.workspace.yaml"),
                                         "--env", str(root / ".toprope/env-library"), "--identity",
                                         f"static:{root / 'ids.yaml'}"],
                "env": {"TOPROPE_TOKEN": TOKENS["agent"]}} for m in DOMAINS}


def run_probe(backend: Any, worlds: Path, p: dict[str, Any], out: Path, how: str, materials: str,
              toolchain: Path | None = None) -> dict[str, Any]:
    """One probe on a copy of its starting state. `toolchain` (the Toprope arm): the deployed
    declarations, whose generated tools the agent uses; otherwise the agent gets the state as
    JSON and `materials` as the rules."""
    from .toolserver import ToolSpec
    root = out / f"{p['id']}-{uuid.uuid4().hex[:6]}"
    shutil.copytree(worlds / p["id"], root)
    situation = json.loads((root / "situation.json").read_text())
    ctx: dict[str, Any] = {"objects": toolchain is None}
    if toolchain is not None:
        for d in DOMAINS:
            shutil.copy(toolchain / d / f"{d}.domain.yaml", root / "toolchain" / d / f"{d}.domain.yaml")
        ctx["servers"] = servers(root)
    t = Transcript(out / f"{p['id']}.jsonl")
    result: dict[str, Any] = {"probe": p["id"]}
    from .blind import check
    check(f"probe {p['id']}'s request", _user(p, situation))     # stops the run: never a probe error
    try:
        result["answer"] = backend.converse(prompt("probe", how=how, materials=materials), _user(p, situation),
                                            ToolSpec("probe", str(root), json.dumps(ctx)), t)
    except Exception as e:
        if type(e).__name__ in ("UsageLimit", "BudgetExceeded"):
            raise
        result["error"] = f"{type(e).__name__}: {str(e)[:500]}"
    outbox = root / "outbox.jsonl"
    result["messages_to_owner"] = [json.loads(x) for x in outbox.read_text().splitlines()] if outbox.exists() else []
    result["transcript"] = t.path.name
    shutil.rmtree(root, ignore_errors=True)
    return result


def run_probes(backend: Any, worlds: Path, probes: list[dict[str, Any]], out: Path, how: str, materials: str,
               toolchain: Path | None = None, jobs: int = 1) -> list[dict[str, Any]]:
    """Every probe, `jobs` at a time. They are independent: each runs on its own copy of its
    starting state and writes its own transcript. The results keep the probes' order. A usage
    limit (or the cost cap) in any of them stops the run once the others have finished."""
    from concurrent.futures import ThreadPoolExecutor
    if jobs <= 1:
        return [run_probe(backend, worlds, p, out, how, materials, toolchain) for p in probes]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_probe, backend, worlds, p, out, how, materials, toolchain) for p in probes]
        results, stop = [], None
        for f in futures:
            try:
                results.append(f.result())
            except Exception as e:                       # noqa: BLE001 - UsageLimit or BudgetExceeded
                stop = stop or e
    if stop is not None:
        raise stop
    return results


__all__ = ["PROBES", "build_worlds", "generic_tools", "load_probes", "probe_tools", "run_probe", "run_probes"]
