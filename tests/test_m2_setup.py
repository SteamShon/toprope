"""M2's setup tools: the draw (experiments/tools/m2_draw.py) and the paper-only check
(experiments/tools/m2_paper.py). No instrument content: the requests here are format filler."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"experiments/tools/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


draw = _load("m2_draw")
paper = _load("m2_paper")
SALT = "ab" * 32
T0 = 1_800_000_000                       # the bases' commit time in these tests


def _git(root, *args, when=T0):
    env = {"GIT_COMMITTER_DATE": f"{when} +0000", "GIT_AUTHOR_DATE": f"{when} +0000", "HOME": str(root),
           "GIT_CONFIG_NOSYSTEM": "1", "PATH": __import__("os").environ["PATH"]}
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=root, env=env,
                   check=True, capture_output=True)


def _fetch(rnd):
    return hashlib.sha256(f"round {rnd}".encode()).digest()


@pytest.fixture
def repo(tmp_path):
    """A repository whose `origin/develop` holds a frozen draw.yaml, then 14 frozen bases; a salt
    outside it."""
    root = tmp_path / "repo"
    (root / "experiments/m2").mkdir(parents=True)
    _git(root, "init", "-q")
    (tmp_path / "salt").write_text(SALT + "\n")
    d = yaml.safe_load((ROOT / "experiments/m2/draw.template.yaml").read_text())
    d.update(salt_sha256=draw.sha256_hex(SALT.encode()), status="frozen")
    (root / draw.DRAW).write_text(yaml.safe_dump(d))
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "prereg", when=T0 - 100)
    reqs = {"requests": [{"seq": i, "intent": f"filler {i}"} for i in range(1, 15)]}
    (tmp_path / "requests.yaml").write_text(yaml.safe_dump(reqs))
    draw.main(["freeze-bases", str(tmp_path / "requests.yaml"), "--out", str(root / draw.BASES)])
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "bases")
    _git(root, "update-ref", "refs/remotes/origin/develop", "HEAD")
    return tmp_path


AFTER = T0 + draw.DELAY + 10


def _types(t, now=AFTER, fetch=_fetch):
    return draw.drawn_all(t / "repo", str(t / "salt"), fetch, now=now)


def test_the_draw_uses_the_beacon_round_an_hour_after_the_bases_landed(repo):
    types, info = _types(repo)
    assert info["round"] == draw.round_at(T0 + draw.DELAY)
    assert types == _types(repo)[0] and len(types) == 14
    bases = json.loads((repo / "repo" / draw.BASES).read_text())["bases"]
    assert types["3"] == draw.draw_one(SALT.encode(), _fetch(info["round"]), 3, bases["3"], info["shares"])
    other = _types(repo, fetch=lambda r: hashlib.sha256(b"another beacon").digest())[0]
    assert other != types                     # the beacon, unknown when the bases froze, decides


def test_the_draw_waits_for_its_round(repo):
    with pytest.raises(SystemExit, match="not out yet.*Fix: run `draw` again after that time"):
        _types(repo, now=T0 + 60)


def test_the_draw_follows_the_shares():
    shares = [("none", 0.3), ("a", 0.2), ("b", 0.5)]
    assert [draw.pick(u, shares) for u in (0.0, 0.2999, 0.3, 0.4999, 0.5, 0.9999)] == ["none", "none", "a", "a", "b", "b"]
    counts = {}
    for seq in range(4000):
        t = draw.draw_one(b"s" * 32, b"r", seq, draw.sha256_hex(str(seq).encode()), shares)
        counts[t] = counts.get(t, 0) + 1
    assert abs(counts["none"] / 4000 - 0.3) < 0.03 and abs(counts["b"] / 4000 - 0.5) < 0.03


def test_the_draw_refuses_a_salt_whose_hash_was_not_committed(repo):
    (repo / "salt").write_text("cd" * 32)
    with pytest.raises(SystemExit, match="does not match the committed `salt_sha256`"):
        _types(repo)


def test_the_draw_refuses_bases_not_on_the_protected_branch(repo):
    _git(repo / "repo", "update-ref", "refs/remotes/origin/develop", "HEAD~1")    # only the prereg landed
    with pytest.raises(SystemExit, match="draw-bases.json is not on origin/develop.*Fix: merge it"):
        _types(repo)


def test_the_draw_refuses_bases_changed_after_they_landed(repo):
    root = repo / "repo"
    (root / draw.BASES).write_text((root / draw.BASES).read_text().replace("frozen_at", "frozen-at"))
    with pytest.raises(SystemExit, match="working copy of experiments/m2/draw-bases.json differs"):
        _types(repo)
    _git(root, "commit", "-qam", "re-freeze", when=T0 + 10)
    _git(root, "update-ref", "refs/remotes/origin/develop", "HEAD")
    with pytest.raises(SystemExit, match="changed on origin/develop after it was first merged"):
        _types(repo)


def test_the_draw_refuses_a_draw_file_not_frozen(repo):
    root = repo / "repo"
    d = yaml.safe_load((root / draw.DRAW).read_text())
    d["status"] = "draft"
    fresh = repo / "fresh"
    (fresh / "experiments/m2").mkdir(parents=True)
    _git(fresh, "init", "-q")
    (fresh / draw.DRAW).write_text(yaml.safe_dump(d))
    (fresh / draw.BASES).write_text((root / draw.BASES).read_text())
    _git(fresh, "add", "-A"); _git(fresh, "commit", "-qm", "both")
    _git(fresh, "update-ref", "refs/remotes/origin/develop", "HEAD")
    with pytest.raises(SystemExit, match="not `status: frozen`"):
        draw.drawn_all(fresh, str(repo / "salt"), _fetch, now=AFTER)


def test_the_draw_refuses_fewer_than_twelve_requests(tmp_path):
    root = tmp_path / "repo"
    (root / "experiments/m2").mkdir(parents=True)
    _git(root, "init", "-q")
    (tmp_path / "salt").write_text(SALT)
    d = yaml.safe_load((ROOT / "experiments/m2/draw.template.yaml").read_text())
    d.update(salt_sha256=draw.sha256_hex(SALT.encode()), status="frozen")
    (root / draw.DRAW).write_text(yaml.safe_dump(d))
    (root / draw.BASES).write_text(json.dumps({"bases": {str(i): "00" * 32 for i in range(1, 12)}}))
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "x")
    _git(root, "update-ref", "refs/remotes/origin/develop", "HEAD")
    with pytest.raises(SystemExit, match="11 requests.*at least 12"):
        draw.drawn_all(root, str(tmp_path / "salt"), _fetch, now=AFTER)


def test_bases_are_frozen_once_and_seqs_do_not_repeat(repo, tmp_path):
    with pytest.raises(SystemExit, match="frozen once"):
        draw.main(["freeze-bases", str(repo / "requests.yaml"), "--out", str(repo / "repo" / draw.BASES)])
    (tmp_path / "dup.yaml").write_text(yaml.safe_dump({"requests": [{"seq": 1, "intent": "a"}, {"seq": 1, "intent": "b"}]}))
    with pytest.raises(SystemExit, match="a `seq` repeats"):
        draw.main(["freeze-bases", str(tmp_path / "dup.yaml"), "--out", str(tmp_path / "b.json")])


def test_the_salt_is_never_made_inside_the_repository(tmp_path):
    with pytest.raises(SystemExit, match="inside the repository.*Fix: write the salt outside"):
        draw.main(["make-salt", str(ROOT / "experiments/m2/salt")])
    draw.main(["make-salt", str(tmp_path / "salt")])
    assert len(draw.read_salt(tmp_path / "salt")) == 64


def test_the_fallback_takes_the_next_type_that_applies():
    shares = [("none", .3), ("a", .2), ("b", .2), ("c", .3)]
    assert draw.applied("a", [], shares) == "a"
    assert draw.applied("a", ["a"], shares) == "b"
    assert draw.applied("b", ["b", "c"], shares) == "none"     # wraps around to the clean control
    assert draw.applied("c", ["c"], shares) == "none"


def _verify(t, key):
    (t / "key.yaml").write_text(yaml.safe_dump(key))
    draw.main(["verify", "--salt", str(t / "salt"), "--root", str(t / "repo"), "--key", str(t / "key.yaml"),
               "--requests", str(t / "requests.yaml")], fetch=_fetch)


def test_verify_catches_a_key_or_a_request_that_departs_from_the_draw(repo, capsys, monkeypatch):
    monkeypatch.setattr(draw.time, "time", lambda: AFTER)
    types, _ = _types(repo)
    seeds = [{"seq": int(s), "drawn": t, "type": t} for s, t in types.items()]
    _verify(repo, {"seeds": seeds})
    assert "all 14 draws match" in capsys.readouterr().out
    other = next(t for t in ("conflicts-with-rule", "none") if t != seeds[0]["type"])
    bad = [dict(seeds[0], type=other)] + seeds[1:]                    # the researcher chose another problem
    with pytest.raises(SystemExit):
        _verify(repo, {"seeds": bad})
    assert f"request {seeds[0]['seq']}: the key uses {other}" in capsys.readouterr().out
    reqs = yaml.safe_load((repo / "requests.yaml").read_text())
    reqs["requests"][1]["intent"] += " (reworded)"                    # a base changed after the draw
    (repo / "requests.yaml").write_text(yaml.safe_dump(reqs))
    with pytest.raises(SystemExit):
        _verify(repo, {"seeds": seeds})
    assert "request 2: its `intent` changed after the bases were frozen" in capsys.readouterr().out


def test_verify_lists_each_not_applicable_reason_and_needs_one(repo, capsys, monkeypatch):
    monkeypatch.setattr(draw.time, "time", lambda: AFTER)
    types, info = _types(repo)
    seq, drawn = next((s, t) for s, t in types.items() if t != "none")
    nxt = draw.applied(drawn, [drawn], info["shares"])
    seeds = [{"seq": int(s), "drawn": t, "type": t} for s, t in types.items() if s != seq]
    seeds.append({"seq": int(seq), "drawn": drawn, "type": nxt, "not_applicable": [{"type": drawn, "why": "filler"}]})
    _verify(repo, {"seeds": seeds})
    assert f"review: request {seq}: {drawn} not applicable: filler" in capsys.readouterr().out
    seeds[-1]["not_applicable"] = [drawn]                             # no reason given
    with pytest.raises(SystemExit):
        _verify(repo, {"seeds": seeds})
    assert "needs `type` and `why`" in capsys.readouterr().out


# --- paper only ---

GOOD = {"command": ["uvx", "alpaca-mcp-server==2.4.1"], "env": {"ALPACA_PAPER_TRADE": "true"},
        "pass_env": ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]}
PAPER_ENV = {"ALPACA_API_KEY": "PKTEST", "ALPACA_SECRET_KEY": "x"}


def test_a_paper_binding_passes():
    assert paper.problems(GOOD, PAPER_ENV) == []


@pytest.mark.parametrize("change, env, says", [
    ({"env": {"ALPACA_PAPER_TRADE": "false"}}, PAPER_ENV, "not exactly `ALPACA_PAPER_TRADE"),
    ({"env": {}}, PAPER_ENV, "not exactly `ALPACA_PAPER_TRADE"),
    ({"env": {"ALPACA_PAPER_TRADE": "true", "ALPACA_API_KEY": "PK1"}}, PAPER_ENV, "not exactly `ALPACA_PAPER_TRADE"),
    ({}, {**PAPER_ENV, "ALPACA_API_KEY": "AKLIVE"}, "not a paper key"),
    ({"pass_env": ["ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_PAPER_TRADE"]}, PAPER_ENV, "not exactly the two keys"),
    ({"command": ["python", "evil.py", "alpaca-mcp-server"]}, PAPER_ENV, "not Alpaca's server pinned"),
    ({"command": ["uvx", "--from", "git+https://x", "alpaca-mcp-server"]}, PAPER_ENV, "not Alpaca's server pinned"),
    ({"command": ["uvx", "alpaca-mcp-server@git+https://x"]}, PAPER_ENV, "not Alpaca's server pinned"),
    ({"command": ["uvx", "alpaca-mcp-server"]}, PAPER_ENV, "not Alpaca's server pinned"),
])
def test_a_binding_that_could_trade_live_is_refused(change, env, says):
    found = paper.problems({**GOOD, **change}, env)
    assert any(says in p and "Fix:" in p for p in found), found


def test_a_url_upstream_is_refused():
    assert "not a command" in paper.problems({"url": "https://example/mcp"}, PAPER_ENV)[0]


def _serve(tmp_path, monkeypatch, *bindings):
    monkeypatch.setattr(paper.os, "environ", PAPER_ENV)
    started = []
    import toprope.proxy.cli as cli
    monkeypatch.setattr(cli, "main", lambda argv: started.append(argv))
    args = ["serve", "--", "--domain", "d.yaml", "--identity", "static:t.yaml"]
    for b in bindings:
        args += [b] if b.startswith("--binding=") else ["--binding", b]
    try:
        paper.main(args)
    except SystemExit:
        pass
    return started


def test_serve_does_not_start_the_proxy_on_a_live_binding(tmp_path, monkeypatch):
    live, good = tmp_path / "live.yaml", tmp_path / "paper.yaml"
    live.write_text(yaml.safe_dump({"upstream": {**GOOD, "env": {"ALPACA_PAPER_TRADE": "false"}}, "tools": {}}))
    good.write_text(yaml.safe_dump({"upstream": GOOD, "tools": {}}))
    assert _serve(tmp_path, monkeypatch, str(live)) == []
    assert _serve(tmp_path, monkeypatch, str(good), f"--binding={live}") == []   # the proxy would load the last
    assert _serve(tmp_path, monkeypatch, str(good))
