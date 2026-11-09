"""`toprope.yaml` gives `toprope-run` its composition options, and the member follows from the
action (ADR-0049, C3)."""
import json
from pathlib import Path

import pytest

from toprope.adapters.cli import infer_member, main, with_config

ROOT = Path(__file__).resolve().parents[1]
SELF = {"composition": "domains/toprope-self.composition.yaml", "kernel_root": ".",
        "workspace": "toprope.authoring.workspace.yaml", "env": ".toprope/env"}


def config(tmp_path, text):
    p = tmp_path / "toprope.yaml"
    p.write_text(text)
    return p


def test_the_file_fills_in_missing_options_relative_to_itself(tmp_path):
    p = config(tmp_path, "composition: c.composition.yaml\nkernel_root: .\nenv: /abs/env\n")
    argv = with_config(["--config", str(p), "--kernel-root", "/given", "get", "x"])
    assert argv[:2] == ["--composition", str(tmp_path / "c.composition.yaml")]
    assert ["--env", "/abs/env"] == argv[argv.index("--env"):argv.index("--env") + 2]
    assert argv.count("--kernel-root") == 1 and "/given" in argv     # the command line wins


def test_the_file_in_the_current_directory_is_read(tmp_path, monkeypatch):
    config(tmp_path, "composition: c.composition.yaml\n")
    monkeypatch.chdir(tmp_path)
    assert with_config(["get", "x"])[:2] == ["--composition", "c.composition.yaml"]


def test_a_domain_a_composition_or_no_config_ignores_the_file(tmp_path, monkeypatch):
    config(tmp_path, "composition: c.composition.yaml\nkernel_root: .\nenv: e\n")
    monkeypatch.chdir(tmp_path)
    assert with_config(["--domain", "d.yaml", "get", "x"]) == ["--domain", "d.yaml", "get", "x"]
    # another composition must not run from this file's kernel root (#202's review)
    assert with_config(["--composition", "o.yaml", "guide"]) == ["--composition", "o.yaml", "guide"]
    assert with_config(["--no-config", "get", "x"]) == ["--no-config", "get", "x"]


@pytest.mark.parametrize("text, says", [
    ("compositon: c.yaml\n", "unknown key(s) compositon; the keys are composition"),
    ("- a\n- b\n", "expected a mapping"),
    ("composition: [a, b]\n", "`composition` must be a single value"),
    ("composition: : :\n", "not valid YAML"),
])
def test_a_bad_file_is_refused_with_its_fix(tmp_path, text, says):
    p = config(tmp_path, text)
    with pytest.raises(SystemExit) as e:
        with_config(["--config", str(p), "get", "x"])
    assert says in str(e.value)


def test_a_missing_config_given_on_the_command_line_is_an_error(tmp_path):
    with pytest.raises(SystemExit, match="no such file"):
        with_config(["--config", str(tmp_path / "nope.yaml"), "get", "x"])


def self_argv(*args):
    return ["--composition", str(ROOT / SELF["composition"]), "--kernel-root", str(ROOT), *args]


def test_the_member_is_the_one_whose_actions_include_the_command():
    assert infer_member(self_argv("deploy", "x"))[:2] == ["--member", "delivery"]
    assert infer_member(self_argv("approve_commit", "x"))[:2] == ["--member", "authoring"]
    assert infer_member(self_argv("--member", "authoring", "get", "x")) == self_argv("--member", "authoring", "get", "x")


def test_a_read_or_an_unknown_action_asks_for_the_member():
    with pytest.raises(SystemExit, match="get: give --member, one of authoring, delivery"):
        infer_member(self_argv("get", "x"))
    with pytest.raises(SystemExit, match="no member of .* has this action"):
        infer_member(self_argv("aprove_commit", "x"))
    with pytest.raises(SystemExit, match="give an action, or --member"):
        infer_member(self_argv())


def test_help_without_a_member_prints_the_options_and_the_members(capsys):
    with pytest.raises(SystemExit) as e:
        infer_member(self_argv("--help"))
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "--config" in out and "authoring, delivery" in out


def test_a_git_identity_in_the_file_is_looked_up_next_to_it(tmp_path):
    p = config(tmp_path, "composition: c.yaml\nidentity: git\n")
    argv = with_config(["--config", str(p), "get", "x"])
    assert argv[argv.index("--identity") + 1] == f"git:{tmp_path / 'toprope.identity.yaml'}"


def test_a_command_with_only_the_file_reads_the_self_domains(tmp_path, capsys):
    p = config(tmp_path, "".join(f"{k}: {ROOT / v}\n" for k, v in SELF.items()))
    main(["--config", str(p), "--member", "authoring", "get", "authoring"])
    assert json.loads(capsys.readouterr().out)["id"] == "authoring"


def test_the_repositorys_file_points_at_the_self_domains(monkeypatch):
    monkeypatch.chdir(ROOT)
    argv = infer_member(with_config(["approve_commit", "x"]))
    opts = dict(zip(argv[0::2], argv[1::2]))
    assert opts["--member"] == "authoring"
    for opt in ("--composition", "--workspace", "--kernel-root"):
        assert Path(opts[opt]).exists(), opt
