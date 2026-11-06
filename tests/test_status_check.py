"""The STATUS.md check (tools/status_check.py) run on every pull request."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("status_check", ROOT / "tools/status_check.py")
status_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status_check)
check = status_check.check

STATUS = """# Status
Updated: 2026-11-06 · Cleaned for release: `v0.1.0`
## Where we are
## Done
## In progress
## Next
## Open questions
"""


def test_work_pr_that_updates_status_passes():
    assert check("develop", "Add x", "", {"docs/STATUS.md", "src/x.py"}, STATUS) == []


def test_work_pr_without_status_change_fails():
    errors = check("develop", "Add x", "", {"src/x.py"}, STATUS)
    assert len(errors) == 1 and "STATUS.md: no change" in errors[0]


def test_sub_pr_into_umbrella_is_checked_too():
    assert check("umbrella/switch-over", "Add x", "", {"src/x.py"}, STATUS)


def test_opt_out_line_with_reason_passes():
    body = "## What and why\n...\nSTATUS.md: no change - typo fix only\n"
    assert check("develop", "Fix typo", body, {"README.md"}, STATUS) == []


def test_opt_out_line_needs_a_reason():
    assert check("develop", "Fix typo", "STATUS.md: no change -   \n", {"README.md"}, STATUS)


def test_opt_out_mentioned_mid_sentence_does_not_count():
    body = "I did not write STATUS.md: no change - yet"
    assert check("develop", "Add x", body, {"src/x.py"}, STATUS)


def test_release_pr_needs_matching_cleanup_marker():
    assert check("main", "Release v0.1.0", "", {"src/x.py"}, STATUS) == []
    errors = check("main", "Release v0.2.0", "", {"docs/STATUS.md"}, STATUS)
    assert len(errors) == 1 and "Cleaned for release: v0.1.0" in errors[0]


def test_release_pr_needs_release_title():
    assert check("main", "Ship things", "", set(), STATUS)


def test_missing_sections_fail_on_any_base():
    broken = STATUS.replace("## Next\n", "")
    errors = check("develop", "Add x", "", {"docs/STATUS.md"}, broken)
    assert errors == ["docs/STATUS.md is missing sections: ## Next."]


def test_missing_status_file_fails():
    assert check("develop", "Add x", "", {"src/x.py"}, None) == ["docs/STATUS.md is missing."]


def test_other_bases_are_not_checked():
    assert check("feat/some-stack", "Add x", "", {"src/x.py"}, STATUS) == []


def test_repository_status_file_has_the_required_sections():
    text = (ROOT / "docs/STATUS.md").read_text()
    assert check("develop", "Add x", "", {"docs/STATUS.md"}, text) == []


def test_cli_exit_codes(tmp_path):
    changed = tmp_path / "changed.txt"
    changed.write_text("src/x.py\n")
    status = tmp_path / "STATUS.md"
    status.write_text(STATUS)
    args = ["--base", "develop", "--title", "Add x", "--changed-files", str(changed), "--status", str(status)]
    assert status_check.main(args) == 1
    changed.write_text("src/x.py\ndocs/STATUS.md\n")
    assert status_check.main(args) == 0
