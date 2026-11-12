"""M2's setup tools: the draw (experiments/tools/m2_draw.py) and the paper-only check
(experiments/tools/m2_paper.py). No instrument content: the requests here are format filler."""
import importlib.util
import json
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


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A salt outside the repository, draw.yaml from the template with its hash, and frozen bases."""
    salt = tmp_path / "salt"
    salt.write_text(SALT + "\n")
    d = yaml.safe_load((ROOT / "experiments/m2/draw.template.yaml").read_text())
    d["salt_sha256"] = draw.sha256_hex(SALT.encode())
    (tmp_path / "draw.yaml").write_text(yaml.safe_dump(d))
    reqs = {"requests": [{"seq": i, "intent": f"filler {i}"} for i in range(1, 15)]}
    (tmp_path / "requests.yaml").write_text(yaml.safe_dump(reqs))
    draw.main(["freeze-bases", str(tmp_path / "requests.yaml"), "--out", str(tmp_path / "bases.json")])
    monkeypatch.setattr(draw, "committed", lambda p: True)
    return tmp_path


def _args(t, *extra):
    return ["--salt", str(t / "salt"), "--draw", str(t / "draw.yaml"), "--bases", str(t / "bases.json"), *extra]


def _drawn(capsys, t):
    capsys.readouterr()
    draw.main(["draw", *_args(t)])
    return dict(line.split("\t") for line in capsys.readouterr().out.splitlines())


def test_the_draw_is_fixed_by_the_salt_and_the_bases(setup, capsys):
    first = _drawn(capsys, setup)
    assert first == _drawn(capsys, setup)
    assert len(first) == 14 and set(first.values()) <= {t["type"] for t in yaml.safe_load((setup / "draw.yaml").read_text())["types"]}
    salt_bytes = SALT.encode()
    bases = json.loads((setup / "bases.json").read_text())["bases"]
    shares, _, _ = draw.load_draw(setup / "draw.yaml")
    assert first["3"] == draw.draw_one(salt_bytes, 3, bases["3"], shares)


def test_the_draw_follows_the_shares():
    shares = [("none", 0.3), ("a", 0.2), ("b", 0.5)]
    assert [draw.pick(u, shares) for u in (0.0, 0.2999, 0.3, 0.4999, 0.5, 0.9999)] == ["none", "none", "a", "a", "b", "b"]
    salt = b"s" * 32
    counts = {}
    for seq in range(4000):
        t = draw.draw_one(salt, seq, draw.sha256_hex(str(seq).encode()), shares)
        counts[t] = counts.get(t, 0) + 1
    assert abs(counts["none"] / 4000 - 0.3) < 0.03 and abs(counts["b"] / 4000 - 0.5) < 0.03


def test_the_draw_refuses_a_salt_whose_hash_was_not_committed(setup, capsys):
    (setup / "salt").write_text("cd" * 32)
    with pytest.raises(SystemExit, match="does not match the committed `salt_sha256`"):
        draw.main(["draw", *_args(setup)])


def test_the_draw_refuses_files_not_committed(setup, monkeypatch):
    monkeypatch.setattr(draw, "committed", lambda p: False)
    with pytest.raises(SystemExit, match="not committed.*Fix: commit draw.yaml and draw-bases.json"):
        draw.main(["draw", *_args(setup)])


def test_the_draw_refuses_fewer_than_twelve_requests(tmp_path, monkeypatch):
    (tmp_path / "salt").write_text(SALT)
    d = yaml.safe_load((ROOT / "experiments/m2/draw.template.yaml").read_text())
    d["salt_sha256"] = draw.sha256_hex(SALT.encode())
    (tmp_path / "draw.yaml").write_text(yaml.safe_dump(d))
    (tmp_path / "bases.json").write_text(json.dumps({"bases": {str(i): "00" * 32 for i in range(1, 12)}}))
    monkeypatch.setattr(draw, "committed", lambda p: True)
    with pytest.raises(SystemExit, match="11 requests.*at least 12"):
        draw.main(["draw", *_args(tmp_path)])


def test_bases_are_frozen_once(setup):
    with pytest.raises(SystemExit, match="frozen once"):
        draw.main(["freeze-bases", str(setup / "requests.yaml"), "--out", str(setup / "bases.json")])


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


def test_verify_catches_a_key_that_departs_from_the_draw(setup, capsys):
    drawn = _drawn(capsys, setup)
    seeds = [{"seq": int(s), "drawn": t, "type": t} for s, t in drawn.items()]
    (setup / "key.yaml").write_text(yaml.safe_dump({"seeds": seeds}))
    draw.main(["verify", *_args(setup, "--key", str(setup / "key.yaml"))])
    assert "all 14 draws match" in capsys.readouterr().out
    other = next(t for t in ("conflicts-with-rule", "none") if t != seeds[0]["type"])
    seeds[0]["type"] = other                          # the researcher chose a different problem
    (setup / "key.yaml").write_text(yaml.safe_dump({"seeds": seeds}))
    with pytest.raises(SystemExit):
        draw.main(["verify", *_args(setup, "--key", str(setup / "key.yaml"))])
    assert f"request {seeds[0]['seq']}: the key uses {other}" in capsys.readouterr().out


# --- paper only ---

GOOD = {"command": ["uvx", "alpaca-mcp-server"], "env": {"ALPACA_PAPER_TRADE": "true"},
        "pass_env": ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]}
PAPER_ENV = {"ALPACA_API_KEY": "PKTEST", "ALPACA_SECRET_KEY": "x"}


def test_a_paper_binding_passes():
    assert paper.problems(GOOD, PAPER_ENV) == []


@pytest.mark.parametrize("change, env, says", [
    ({"env": {"ALPACA_PAPER_TRADE": "false"}}, PAPER_ENV, "does not set `ALPACA_PAPER_TRADE"),
    ({"env": {}}, PAPER_ENV, "does not set `ALPACA_PAPER_TRADE"),
    ({}, {**PAPER_ENV, "ALPACA_API_KEY": "AKLIVE"}, "not a paper key"),
    ({"pass_env": ["ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_PAPER_TRADE"]}, PAPER_ENV, "could turn paper off"),
    ({"env": {"ALPACA_PAPER_TRADE": "true", "ALPACA_API_KEY": "PK1"}}, PAPER_ENV, "writes `ALPACA_API_KEY` itself"),
    ({"env": {"ALPACA_PAPER_TRADE": "true", "TRADE_API_URL": "https://api.alpaca.markets"}}, PAPER_ENV, "live API"),
    ({"command": ["python", "my_broker.py"]}, PAPER_ENV, "does not run `alpaca-mcp-server`"),
])
def test_a_binding_that_could_trade_live_is_refused(change, env, says):
    found = paper.problems({**GOOD, **change}, env)
    assert any(says in p and "Fix:" in p for p in found), found


def test_a_url_upstream_is_refused():
    assert "not a command" in paper.problems({"url": "https://example/mcp"}, PAPER_ENV)[0]


def test_serve_does_not_start_the_proxy_on_a_live_binding(tmp_path, monkeypatch):
    b = tmp_path / "binding.yaml"
    b.write_text(yaml.safe_dump({"upstream": {**GOOD, "env": {"ALPACA_PAPER_TRADE": "false"}}, "tools": {}}))
    monkeypatch.setattr(paper.os, "environ", PAPER_ENV)
    started = []
    import toprope.proxy.cli as cli
    monkeypatch.setattr(cli, "main", lambda argv: started.append(argv))
    with pytest.raises(SystemExit):
        paper.main(["serve", "--", "--domain", "d.yaml", "--binding", str(b), "--identity", "static:t.yaml"])
    assert started == []
    b.write_text(yaml.safe_dump({"upstream": GOOD, "tools": {}}))
    paper.main(["serve", "--", "--domain", "d.yaml", "--binding", str(b), "--identity", "static:t.yaml"])
    assert started and started[0][3] == str(b)
