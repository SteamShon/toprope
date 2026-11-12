"""tools/run_archive.py (ADR-0055): raw run records leave the tree, and come back unchanged."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_archive", ROOT / "tools/run_archive.py")
ra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ra)


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=root,
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A repository with one committed run: two arms, a scoring directory with transcripts."""
    root = tmp_path / "repo"
    run = root / "experiments/m9/runs/r1"
    for f, text in {"nl/c1/out.json": "nl", "toprope/c1/out.json": "tp", "scoring/metrics.json": "{}",
                    "scoring/labels.yaml": "l", "scoring/transcripts/t1.json": "t", "summary.json": "s"}.items():
        (run / f).parent.mkdir(parents=True, exist_ok=True)
        (run / f).write_text(text)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "run")
    return root, run


def _ns(**kw):
    import argparse
    return argparse.Namespace(**kw)


def test_split_keeps_the_summary_and_moves_the_raw_records_to_history(repo):
    root, run = repo
    ra.cmd_split(_ns(run=str(run), all_dirs=False, commit="HEAD"), root=root)
    raw = json.loads((run / "RAW.json").read_text())["raw"]
    assert sorted(raw) == ["nl", "scoring/transcripts", "toprope"]
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "split")
    tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout.split()
    assert "experiments/m9/runs/r1/scoring/metrics.json" in tracked and "experiments/m9/runs/r1/summary.json" in tracked
    assert not [t for t in tracked if "/nl/" in t or "/transcripts/" in t]
    ra.cmd_check(_ns(), root=root)


def test_restore_brings_back_exactly_what_was_split(repo):
    root, run = repo
    ra.cmd_split(_ns(run=str(run), all_dirs=False, commit="HEAD"), root=root)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "split")
    subprocess.run(["rm", "-rf", str(run / "nl"), str(run / "scoring/transcripts")], check=True)
    ra.cmd_restore(_ns(run=str(run)), root=root)
    assert (run / "nl/c1/out.json").read_text() == "nl" and (run / "scoring/transcripts/t1.json").read_text() == "t"
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
    assert status == ""                                   # restored copies stay out of the next commit


def test_restore_refuses_a_record_that_does_not_match_its_commit(repo):
    root, run = repo
    ra.cmd_split(_ns(run=str(run), all_dirs=False, commit="HEAD"), root=root)
    m = json.loads((run / "RAW.json").read_text())
    m["raw"]["nl"] = "0" * 40
    (run / "RAW.json").write_text(json.dumps(m))
    subprocess.run(["rm", "-rf", str(run / "nl")], check=True)
    with pytest.raises(SystemExit, match="not the recorded.*Fix:"):
        ra.cmd_restore(_ns(run=str(run)), root=root)


def test_check_fails_when_a_raw_path_is_committed_again(repo):
    root, run = repo
    ra.cmd_split(_ns(run=str(run), all_dirs=False, commit="HEAD"), root=root)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "split")
    _git(root, "add", "-f", "experiments/m9/runs/r1/nl")
    with pytest.raises(SystemExit):
        ra.cmd_check(_ns(), root=root)


def test_pack_is_reproducible_and_fetch_checks_every_hash(tmp_path):
    src = tmp_path / "run"
    (src / "a").mkdir(parents=True)
    (src / "a/x.json").write_text("x")
    (src / "y.txt").write_text("y")
    ra.cmd_pack(_ns(dir=str(src), out=str(tmp_path / "1.tar.gz"), manifest=str(tmp_path / "m1.json"), url=None))
    (src / "y.txt").touch()                                 # a new mtime changes nothing
    ra.cmd_pack(_ns(dir=str(src), out=str(tmp_path / "2.tar.gz"), manifest=str(tmp_path / "m2.json"), url=None))
    assert (tmp_path / "1.tar.gz").read_bytes() == (tmp_path / "2.tar.gz").read_bytes()
    ra.cmd_fetch(_ns(manifest=str(tmp_path / "m1.json"), into=str(tmp_path / "out"), file=str(tmp_path / "1.tar.gz")))
    assert (tmp_path / "out/a/x.json").read_text() == "x"
    m = json.loads((tmp_path / "m1.json").read_text())
    m["sha256"] = "0" * 64
    (tmp_path / "m1.json").write_text(json.dumps(m))
    with pytest.raises(SystemExit, match="sha256 differs"):
        ra.cmd_fetch(_ns(manifest=str(tmp_path / "m1.json"), into=str(tmp_path / "o2"), file=str(tmp_path / "1.tar.gz")))


def test_phase_b_names_the_restore_when_a_runs_raw_records_are_not_here(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "experiments/m1"))
    from phase_b import run as runner
    (tmp_path / "RAW.json").write_text(json.dumps({"source_commit": "c", "raw": {"nl": "t"}}))
    with pytest.raises(SystemExit, match="Fix: python tools/run_archive.py restore"):
        runner.main(["score", "--out", str(tmp_path)])
