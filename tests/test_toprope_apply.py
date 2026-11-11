"""A person applies a human request at their own terminal, with one confirmation (ADR-0053, 3):
the same render, run and record as the GitHub workflow, as the person git identifies."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import human_request as hr  # noqa: E402

from toprope.adapters.cli import apply as cli_apply  # noqa: E402

ANA = "ana <ana@example.com>"
IDS = {"people": {"ana@example.com": {"name": "ana", "github": "Ana-GH", "roles": ["owner", "approver"]}},
       "agents": {"bot@example.com": {"name": "bot", "roles": ["owner"], "on_behalf_of": "ana@example.com",
                                      "grant": {"id": "drafting", "actions": ["propose_element"]}}}}
REQUEST = ".toprope/requests/r.yaml"
REAL_RUN = subprocess.run


class Terminal:
    def __init__(self, tty=True):
        self.tty = tty

    def isatty(self):
        return self.tty


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A directory with the identity file, the person's git email and TLC set; no real kernel."""
    (tmp_path / "toprope.identity.yaml").write_text(yaml.safe_dump(IDS))
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\temail = ana@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv(hr.TLC_ENV, "tla2tools.jar")
    monkeypatch.setattr(sys, "stdin", Terminal())
    return tmp_path


def as_agent(repo):
    (repo / "gitconfig").write_text("[user]\n\temail = bot@example.com\n")


def risk(root, commit, level):
    p = root / ".toprope/commits/authoring/checks.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"commit": commit, "check": "risk", "ok": level == "low", "summary": level}) + "\n")


def nine_steps():
    req = hr.change("authoring")
    req["steps"] += hr.ship(hr.MADE, "authoring")["steps"]
    return req


def write_request(root, req):
    (root / REQUEST).parent.mkdir(parents=True, exist_ok=True)
    (root / REQUEST).write_text(yaml.safe_dump(req, sort_keys=False))


class Kernel:
    """Stands in for `toprope-run`: records each command and the environment it got."""

    def __init__(self, fails=None):
        self.cmds, self.envs, self.fails = [], [], fails

    def __call__(self, cmd, **kw):
        if cmd[0] == "git":                       # the caller's git email: the real git
            return REAL_RUN(cmd, **kw)
        self.cmds.append(cmd)
        self.envs.append(kw.get("env") or {})
        action = cmd[cmd.index("--identity") + 2]
        if action == self.fails:
            return subprocess.CompletedProcess(cmd, 1, "", "the preview environment is down")
        then = [{"kernel": "commit", "reply": "record_commit", "status": "ok", "object": "7-c0ffee"}] \
            if action == "commit_draft" else []
        out = {"status": "ok", "then": then, **({"harness": "12 scenarios passed"} if action == "preview" else {})}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(out), "")

    def actions(self):
        return [c[c.index("--identity") + 2] for c in self.cmds]


def answers(*said):
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return said[len(asked) - 1]
    ask.asked = asked
    return ask


def forge(person, pid):
    """What a process with no terminal could write: the record of an apply, naming `pid` as it."""
    import secrets
    token = secrets.token_hex(16)
    cli_apply._dir().mkdir(mode=0o700, exist_ok=True)
    fd = os.open(cli_apply._file(token), os.O_CREAT | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"as": person, "pid": pid}))
    return token


class on_a_terminal:
    """Standard input is a terminal (a pseudo-terminal) for the processes started meanwhile."""

    def __enter__(self):
        self.master, self.slave = os.openpty()
        self.saved = os.dup(0)
        os.dup2(self.slave, 0)

    def __exit__(self, *exc):
        os.dup2(self.saved, 0)
        for fd in (self.saved, self.slave, self.master):
            os.close(fd)


def runs(root):
    return [json.loads(x) for x in (root / hr.APPROVAL_RUNS).read_text().splitlines()]


def test_a_low_risk_request_runs_every_step_on_one_confirmation(repo, monkeypatch, capsys):
    kernel = Kernel()
    monkeypatch.setattr(hr.subprocess, "run", kernel)
    risk(repo, "7-c0ffee", "low")
    write_request(repo, nine_steps())
    ask = answers("yes")
    out = hr.apply(REQUEST, cwd=repo, ask=ask)
    assert len(ask.asked) == 1 and ANA in ask.asked[0]                 # one confirmation
    shown = capsys.readouterr().out
    assert shown.startswith(hr.render(nine_steps(), repo, "local"))     # what the run page shows, locally worded
    assert "the run is held after the preview" in shown and "has no recorded risk yet" in shown
    assert kernel.actions() == ["confirm_all_proposed", "commit_draft", "check_commit", "approve_commit",
                                "deliver", "preview", "deploy", "run_probes", "verify"]
    assert all(c[c.index("--identity") + 1] == "git:toprope.identity.yaml" for c in kernel.cmds)
    tokens = {e.get(cli_apply.APPLY_ENV) for e in kernel.envs}
    assert len(tokens) == 1 and None not in tokens and "" not in tokens   # the one confirmation
    assert (out["steps"], out["as"], out["channel"]) == (9, ANA, "local") and "failed" not in out
    (row,) = runs(repo)
    assert (row["channel"], row["as"], row["approver"]) == ("local", ANA, "ana@example.com")
    assert row["run"].startswith("local:") and row["steps"] == nine_steps()["steps"]
    assert not (repo / REQUEST).exists()                                 # removed, as the workflow does
    assert not cli_apply._file(tokens.pop()).exists()                    # the token is gone


def test_without_a_terminal_it_is_refused_and_names_the_github_route(repo, monkeypatch):
    kernel = Kernel()
    monkeypatch.setattr(hr.subprocess, "run", kernel)
    monkeypatch.setattr(sys, "stdin", Terminal(tty=False))
    write_request(repo, nine_steps())
    with pytest.raises(SystemExit) as e:
        hr.apply(REQUEST, cwd=repo, ask=answers("yes"))
    assert "needs a person at a terminal" in str(e.value) and "human-request" in str(e.value)
    assert kernel.cmds == [] and (repo / REQUEST).exists() and not (repo / hr.APPROVAL_RUNS).exists()


def test_an_agent_or_an_unlisted_caller_is_refused(repo, monkeypatch):
    kernel = Kernel()
    monkeypatch.setattr(hr.subprocess, "run", kernel)
    write_request(repo, nine_steps())
    as_agent(repo)
    ask = answers("yes")
    with pytest.raises(SystemExit, match=r"bot <bot@example.com> is an agent: only a person applies a request.*Fix: "):
        hr.apply(REQUEST, cwd=repo, ask=ask)
    (repo / "gitconfig").write_text("[user]\n\temail = mallory@example.com\n")
    with pytest.raises(SystemExit, match="mallory@example.com is not listed"):
        hr.apply(REQUEST, cwd=repo, ask=ask)
    assert ask.asked == [] and kernel.cmds == []


def test_an_answer_other_than_yes_runs_nothing(repo, monkeypatch):
    kernel = Kernel()
    monkeypatch.setattr(hr.subprocess, "run", kernel)
    write_request(repo, nine_steps())
    with pytest.raises(SystemExit, match="not applied: nothing was run"):
        hr.apply(REQUEST, cwd=repo, ask=answers("y"))
    assert kernel.cmds == [] and (repo / REQUEST).exists()


def test_a_high_risk_request_stops_after_the_preview_and_ships_on_a_second_apply(repo, monkeypatch, capsys):
    """ADR-0050, 3: the person reads the preview before the commit is put in use."""
    kernel = Kernel()
    monkeypatch.setattr(hr.subprocess, "run", kernel)
    risk(repo, "7-c0ffee", "high: an invariant or outcome rule changed: invariant:x")
    write_request(repo, hr.change("authoring"))                    # what toprope-change writes for high risk
    out = hr.apply(REQUEST, cwd=repo, ask=answers("yes"), with_ship=True)
    assert kernel.actions() == ["confirm_all_proposed", "commit_draft", "check_commit", "approve_commit",
                                "deliver", "preview"]                  # not deploy on the same confirmation
    assert out["held"] == {"step": 7, "number": 7, "commit": "7-c0ffee", "risk": "high"}
    shown = capsys.readouterr().out
    assert "stops after its preview" in shown and "12 scenarios passed" in shown   # the preview, to read
    left = hr.load(repo / REQUEST)
    assert [(s["run"]["action"], s["run"]["target"]) for s in left["steps"]] == [
        ("deploy", "authoring:7-c0ffee:local"), ("run_probes", "authoring:7-c0ffee:local"),
        ("verify", "authoring:7-c0ffee:local")]
    (first,) = runs(repo)
    assert (first["ran"], first["held"]["commit"], first["channel"]) == (6, "7-c0ffee", "local")

    kernel.cmds.clear()
    capsys.readouterr()
    hr.apply(REQUEST, cwd=repo, ask=answers("yes"))                    # after reading the preview
    shown = capsys.readouterr().out
    assert "**Risk recorded on `7-c0ffee`:** high: an invariant or outcome rule changed" in shown
    assert kernel.actions() == ["deploy", "run_probes", "verify"]
    assert not (repo / REQUEST).exists() and len(runs(repo)) == 2      # two approvals in all


def test_the_workflow_still_refuses_to_ship_a_high_risk_commit_it_approved(repo, monkeypatch):
    monkeypatch.setattr(hr.subprocess, "run", Kernel())
    risk(repo, "7-c0ffee", "high: x")
    with pytest.raises(SystemExit, match="7-c0ffee is not low risk"):
        hr.run(nine_steps(), "ana-gh", cwd=repo)


def test_a_failed_step_keeps_the_work_before_it_and_leaves_the_rest_to_apply(repo, monkeypatch, capsys):
    kernel = Kernel(fails="preview")
    monkeypatch.setattr(hr.subprocess, "run", kernel)
    risk(repo, "7-c0ffee", "low")
    write_request(repo, nine_steps())
    with pytest.raises(SystemExit) as e:
        hr.apply(REQUEST, cwd=repo, ask=answers("yes"))
    msg = str(e.value.code)
    assert msg.startswith("step 6 of 9 failed; steps 1-5 ran and their work is kept")
    assert msg.endswith(f"Fix: {hr.LOCAL_AGAIN}") and "push" not in msg.split("Fix:")[1]
    (row,) = runs(repo)
    assert (row["ran"], row["failed"]["step"], row["channel"]) == (5, 6, "local")
    left = hr.load(repo / REQUEST)
    assert left["summary"].endswith("(the rest: steps 6-9 of 9)")
    assert [s["run"]["action"] for s in left["steps"]] == ["preview", "deploy", "run_probes", "verify"]

    kernel.cmds.clear()
    kernel.fails = None
    hr.apply(REQUEST, cwd=repo, ask=answers("yes"))                    # fixed, applied again
    assert kernel.actions() == ["preview", "deploy", "run_probes", "verify"]   # nothing taken twice
    assert not (repo / REQUEST).exists()


def test_an_approval_needs_tlc_before_the_person_is_asked(repo, monkeypatch):
    monkeypatch.delenv(hr.TLC_ENV)
    monkeypatch.setattr(hr.subprocess, "run", Kernel())
    write_request(repo, nine_steps())
    ask = answers("yes")
    with pytest.raises(SystemExit, match="TOPROPE_TLC_JAR is not set: nothing was run"):
        hr.apply(REQUEST, cwd=repo, ask=ask)
    assert ask.asked == []


def test_the_token_stands_only_for_its_own_person_and_process(tmp_path):
    from toprope.identity import Caller
    from toprope.types import Actor
    ana, eli = Caller(Actor(ANA, "person", ())), Caller(Actor("eli <eli@example.com>", "person", ()))
    check = ("import json, os, sys; from toprope.adapters.cli.apply import confirmed_by_apply; "
             "from toprope.identity import Caller; from toprope.types import Actor; "
             "print(json.dumps([confirmed_by_apply(Caller(Actor(i, 'person', ()))) for i in sys.argv[1:]]))")
    with cli_apply.confirmation(ANA) as token:
        env = {**os.environ, cli_apply.APPLY_ENV: token}
        r = subprocess.run([sys.executable, "-c", check, ANA, eli.actor.id], env=env, capture_output=True,
                           text=True, check=True)
        assert json.loads(r.stdout) == [True, False]              # a child of the apply, the person who confirmed
        os.environ[cli_apply.APPLY_ENV] = token
        try:
            assert not cli_apply.confirmed_by_apply(ana)          # not a child of the process that asked
        finally:
            del os.environ[cli_apply.APPLY_ENV]
    r = subprocess.run([sys.executable, "-c", check, ANA], env=env, capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == [False]                        # the apply ended: the token is gone


def test_a_person_only_step_runs_under_the_one_confirmation_and_not_without_it(tmp_path, monkeypatch, capsys):
    """The self domains, from a copy of the repository, with the real `toprope-run`: confirming
    the proposals asks for no second prompt under `apply`, and without it is refused (no terminal)."""
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    for name in filter(None, files):
        src, dst = ROOT / name.decode(), tmp_path / name.decode()
        if "/events/" in name.decode() or not src.is_file():
            continue                   # start from empty logs
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    (tmp_path / "toprope.identity.yaml").write_text(yaml.safe_dump(IDS))
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\temail = ana@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("PATH", str(ROOT / ".venv/bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    from toprope.workspace import Workspace
    ws = Workspace(tmp_path / "toprope.authoring.workspace.yaml")
    ref = next(c.ref for c in ws.chunks("records"))
    rule = {"id": "drafts-name-their-declaration", "on": "Draft", "check": "exists(target.declaration)",
            "reason": "A draft is the working copy of one declaration."}
    ws.propose(f"invariants.{rule['id']}", rule, ref)
    req = {"summary": "Open the draft and confirm what is proposed", "steps": [
        {"run": {"member": "authoring", "action": "open_draft", "target": "authoring",
                 "params": {"domain_id": "authoring", "declaration": "domains/authoring/authoring.domain.yaml",
                            "branch": "work"}}},
        {"run": {"member": "authoring", "action": "confirm_all_proposed", "target": "authoring"}}]}
    write_request(tmp_path, req)
    by_hand = hr.command(req["steps"][1], identity="git:toprope.identity.yaml")
    r = subprocess.run(by_hand, cwd=tmp_path, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert r.returncode != 0 and "requires a person" in r.stderr     # no terminal, no apply: refused
    # The review's reproduction: a script with no terminal forges the record of an apply, naming
    # itself as the parent, and passes the token. Refused: the token never stands in for a terminal.
    token = forge(ANA, os.getpid())
    r = subprocess.run(by_hand, cwd=tmp_path, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       env={**os.environ, cli_apply.APPLY_ENV: token})
    assert r.returncode != 0 and "the apply's confirmation did not reach this step" in r.stderr, r.stderr
    monkeypatch.setattr(sys, "stdin", Terminal())
    with on_a_terminal():                                           # the steps inherit the apply's terminal
        out = hr.apply(REQUEST, cwd=tmp_path, ask=answers("yes"))
    assert out["steps"] == 2 and "failed" not in out
    decl = yaml.safe_load((tmp_path / "domains/authoring/authoring.domain.yaml").read_text())
    (added,) = [i for i in decl["invariants"] if i["id"] == rule["id"]]
    assert added["status"] == "confirmed"
    entry = json.loads((tmp_path / "domains/authoring/interview.jsonl").read_text().splitlines()[-1])
    assert entry["who"] == ANA


def test_the_command_runs_the_repository_s_runner(repo, monkeypatch):
    with pytest.raises(SystemExit, match="no tools/human_request.py here.*Fix: run it from the repository root"):
        cli_apply.runner(repo)
    called = []
    monkeypatch.setattr(cli_apply, "runner", lambda root: type("R", (), {
        "apply": staticmethod(lambda *a, **kw: called.append((a, kw)))}))
    cli_apply.main([REQUEST, "--ship"])
    assert called == [((REQUEST, "toprope.identity.yaml", "."), {"with_ship": True})]


def test_the_repository_runner_loads(monkeypatch):
    assert callable(cli_apply.runner(ROOT).apply)


def test_a_forged_token_without_a_terminal_is_refused_and_a_bad_one_never_prompts(monkeypatch):
    """#244's review: any process could write a token record naming itself; the token alone passed
    `toprope-run`'s person prompt with no terminal. A token that does not check out must refuse,
    not prompt (the prompt would go to a captured stdout while input() waits)."""
    from toprope.adapters.cli import _confirm_on_terminal
    from toprope.identity import Caller
    from toprope.identity.git import GitIdentity
    from toprope.types import Actor
    ana = Caller(Actor(ANA, "person", ()))
    ident = GitIdentity.__new__(GitIdentity)
    token = forge(ANA, os.getppid())                       # names this process's parent, as a step's would
    monkeypatch.setenv(cli_apply.APPLY_ENV, token)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("prompted"))
    monkeypatch.setattr(sys, "stdin", Terminal(tty=False))
    with pytest.raises(SystemExit, match="the apply's confirmation did not reach this step.*Fix: "):
        _confirm_on_terminal(ident, ana, "confirm_all_proposed", "authoring")
    monkeypatch.setattr(sys, "stdin", Terminal(tty=True))
    _confirm_on_terminal(ident, ana, "confirm_all_proposed", "authoring")   # a terminal and the record: taken
    monkeypatch.setenv(cli_apply.APPLY_ENV, forge(ANA, os.getpid()))        # not this process's parent
    with pytest.raises(SystemExit, match="did not reach this step"):
        _confirm_on_terminal(ident, ana, "confirm_all_proposed", "authoring")


def test_ctrl_c_mid_apply_records_what_ran_and_leaves_the_rest(repo, monkeypatch):
    kernel = Kernel()

    def run(cmd, **kw):
        if cmd[0] != "git" and cmd[cmd.index("--identity") + 2] == "preview":
            raise KeyboardInterrupt
        return kernel(cmd, **kw)
    monkeypatch.setattr(hr.subprocess, "run", run)
    risk(repo, "7-c0ffee", "low")
    write_request(repo, nine_steps())
    with pytest.raises(SystemExit) as e:
        hr.apply(REQUEST, cwd=repo, ask=answers("yes"))
    assert e.value.code not in (0, None) and "interrupted (Ctrl-C)" in str(e.value.code)
    (row,) = runs(repo)
    assert (row["ran"], row["failed"]["step"], row["channel"]) == (5, 6, "local")
    assert [s["run"]["action"] for s in hr.load(repo / REQUEST)["steps"]] == ["preview", "deploy", "run_probes",
                                                                             "verify"]


def test_the_token_lives_in_a_private_directory_and_goes_on_sigterm(tmp_path, monkeypatch):
    import signal
    monkeypatch.setattr(cli_apply.tempfile, "gettempdir", lambda: str(tmp_path))
    with cli_apply.confirmation(ANA) as token:
        f = cli_apply._file(token)
        assert oct(f.stat().st_mode & 0o777) == "0o600" and oct(cli_apply._dir().stat().st_mode & 0o777) == "0o700"
        with pytest.raises(KeyboardInterrupt):                # SIGTERM stops it like Ctrl-C
            os.kill(os.getpid(), signal.SIGTERM)
            import time
            time.sleep(5)
    assert not f.exists()
    cli_apply._dir().chmod(0o755)                              # opened to others: refused
    with pytest.raises(SystemExit, match="not a directory only you own and use.*Fix: "):
        with cli_apply.confirmation(ANA):
            pass
    cli_apply._dir().chmod(0o700)
    token = forge(ANA, os.getppid())
    cli_apply._file(token).chmod(0o644)                        # a record others could have written
    monkeypatch.setenv(cli_apply.APPLY_ENV, token)
    from toprope.identity import Caller
    from toprope.types import Actor
    assert not cli_apply.confirmed_by_apply(Caller(Actor(ANA, "person", ())))
