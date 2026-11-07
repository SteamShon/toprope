"""The self domains' logs only grow along one line (tools/logs_check.py, #124's review)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import logs_check  # noqa: E402


def git(cwd, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=cwd, check=True,
                   capture_output=True)


def test_a_branch_that_ran_the_loop_apart_from_the_base_is_refused(tmp_path, monkeypatch):
    log = tmp_path / ".toprope/commits/authoring/log.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text('{"seq": 4}\n')
    git(tmp_path, "init", "-q", "-b", "base")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "4")
    git(tmp_path, "switch", "-qc", "ok")
    log.write_text('{"seq": 4}\n{"seq": 5, "id": "5-ours"}\n')
    git(tmp_path, "commit", "-qam", "5 after 4")
    git(tmp_path, "switch", "-q", "base")
    log.write_text('{"seq": 4}\n{"seq": 5, "id": "5-theirs"}\n')
    git(tmp_path, "commit", "-qam", "5 on the base")
    monkeypatch.chdir(tmp_path)
    assert logs_check.check("base", "base") == []
    (err,) = logs_check.check("base", "ok")                     # both made a commit 5 from 4
    assert err.startswith(".toprope/commits/authoring/log.jsonl: line 2 differs")
    git(tmp_path, "switch", "-qc", "grown", "base")
    log.write_text(log.read_text() + '{"seq": 6}\n')
    git(tmp_path, "commit", "-qam", "6")
    assert logs_check.check("base", "grown") == []


def test_the_approval_run_log_only_grows_too(tmp_path, monkeypatch):
    runs = tmp_path / ".toprope/approval-runs.jsonl"
    runs.parent.mkdir(parents=True)
    runs.write_text('{"run": "https://github.com/o/r/actions/runs/1"}\n')
    git(tmp_path, "init", "-q", "-b", "base")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "run 1")
    git(tmp_path, "switch", "-qc", "rewritten")
    runs.write_text('{"run": "https://github.com/o/r/actions/runs/2"}\n')     # an approval record replaced
    git(tmp_path, "commit", "-qam", "run 2 instead")
    monkeypatch.chdir(tmp_path)
    (err,) = logs_check.check("base", "rewritten")
    assert err.startswith(".toprope/approval-runs.jsonl: line 1 differs")
