"""Local identity from git (ADR-0037, resolved 2): `toprope-run` as yourself, with no token."""
import io
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from test_decl import schema_doc_domain

from toprope.adapters.cli import main
from toprope.decl import load_domain
from toprope.identity.git import GitIdentity, load_table

ROOT = Path(__file__).resolve().parent.parent
TABLE = {
    "people": {"ana@example.com": {"name": "ana", "roles": ["approver"]},
               "eli@example.com": {"name": "eli", "roles": ["eng"]}},
    "agents": {"bot@example.com": {"name": "bot", "roles": ["approver"], "on_behalf_of": "ana@example.com",
                                   "grant": {"id": "g1", "actions": ["approve_experiment"]}}},
}


def repo(tmp_path, email):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    if email:
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", email], check=True)
    (tmp_path / "toprope.identity.yaml").write_text(yaml.safe_dump(TABLE))
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["requires"] = "human"
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    return tmp_path


def set_email(root, email):
    subprocess.run(["git", "-C", str(root), "config", "user.email", email], check=True)


def test_the_git_email_resolves_to_the_listed_person_or_agent(tmp_path):
    root = repo(tmp_path, "ana@example.com")
    ident = GitIdentity(root / "toprope.identity.yaml", root)
    c = ident.resolve(None)
    assert (c.actor.id, c.actor.kind, c.actor.roles) == ("ana <ana@example.com>", "person", ("approver",))
    assert ident.resolve("any-token") == c                              # credentials are not used
    set_email(root, "bot@example.com")
    b = ident.resolve(None)
    assert b.actor.kind == "agent" and b.on_behalf_of.id == "ana <ana@example.com>"
    assert b.grant.actions == frozenset({"approve_experiment"})
    set_email(root, "mallory@example.com")
    assert ident.resolve(None) is None and "mallory@example.com is not listed" in ident.explain()


@pytest.mark.parametrize("bad, where", [
    ({"people": {"a@x": {"roles": "owner"}}}, "people.a@x"),                         # a bare string
    ({"agents": {"b@x": {"roles": ["owner"], "on_behalf_of": "nobody@x", "grant": {"id": "g"}}}}, "agents.b@x"),
    ({"people": {"a@x": {"roles": []}}, "agents": {"b@x": {"roles": [], "on_behalf_of": "a@x"}}}, "agents.b@x"),
    ({"tokens": {}}, "people"),
])
def test_a_malformed_identity_file_is_refused(tmp_path, bad, where):
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match=where):
        load_table(tmp_path / "ids.yaml")


def cli(root, *a):
    return subprocess.run(["uv", "run", "--quiet", "--project", str(ROOT), "toprope-run", "--domain", "d.domain.yaml",
                           "--store", "sqlite:e.db", *a], cwd=root, capture_output=True, text=True, timeout=120,
                          check=False, env={k: v for k, v in os.environ.items() if k != "TOPROPE_TOKEN"})


def test_toprope_run_uses_your_git_identity_by_default(tmp_path):
    root = repo(tmp_path, "eli@example.com")
    who = cli(root, "whoami")
    assert who.returncode == 0 and json.loads(who.stdout) == {"id": "eli <eli@example.com>", "kind": "person",
                                                             "roles": ["eng"]}
    first = cli(root, "--seed", "launch_experiment", "E-onboarding")             # draft: denied by the matrix
    assert first.returncode == 1 and json.loads(first.stdout)["code"] == "matrix"
    set_email(root, "mallory@example.com")
    out = cli(root, "launch_experiment", "E-onboarding")
    assert out.returncode == 1 and "mallory@example.com is not listed" in out.stderr


def test_an_action_that_requires_a_person_needs_your_terminal(tmp_path, monkeypatch):
    root = repo(tmp_path, "ana@example.com")
    out = cli(root, "--seed", "approve_experiment", "E-onboarding", "--note", "ok")   # no terminal here
    assert out.returncode == 1 and "requires a person. Fix: run it yourself on a terminal" in out.stderr
    monkeypatch.chdir(root)
    monkeypatch.setattr("sys.stdin", type("Tty", (io.StringIO,), {"isatty": lambda self: True})("y\n"))
    main(["--domain", "d.domain.yaml", "--store", "sqlite:e.db", "approve_experiment", "E-onboarding", "--note", "ok"])
    assert json.loads(cli(root, "get", "E-onboarding").stdout)["approved_by"] == "ana <ana@example.com>"


def test_an_agent_git_identity_cannot_take_a_person_only_action(tmp_path):
    root = repo(tmp_path, "bot@example.com")
    out = cli(root, "--seed", "approve_experiment", "E-onboarding", "--note", "ok")
    assert out.returncode == 1 and json.loads(out.stdout)["reason"] == (
        "Only a person can approve_experiment. Fix: ask a person to take it: on their terminal, or from a cloud session "
        "through a human request they approve in GitHub (`toprope-change` writes one for a change; "
        "`tools/human_request.py` for any step)")


def test_the_repository_identity_file_grants_agents_no_person_only_action():
    table = load_table(ROOT / "toprope.identity.yaml")
    human = {n for f in ("authoring/authoring", "delivery/delivery")
             for n, a in load_domain(ROOT / f"domains/{f}.domain.yaml").actions.items() if a.requires == "human"}
    agents = [c for c in table.values() if c.actor.kind == "agent"]
    assert human and agents and all(not (c.grant.actions & human) for c in agents)


def test_a_repeated_email_is_refused(tmp_path):
    (tmp_path / "ids.yaml").write_text("people:\n  a@x: {roles: [owner]}\n  a@x: {roles: [expert]}\n")
    with pytest.raises(ValueError, match="duplicate key"):
        load_table(tmp_path / "ids.yaml")


def test_a_given_token_is_not_ignored_for_the_default_git_identity(tmp_path):
    root = repo(tmp_path, "eli@example.com")
    out = cli(root, "--token", "t-1", "whoami")
    assert out.returncode == 1 and "--identity is required" in out.stderr
