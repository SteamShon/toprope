"""Check that a pull request keeps docs/STATUS.md current (AGENTS.md, "Progress").

Run by .github/workflows/status.yml on every pull request. Locally:

    uv run python tools/status_check.py --base develop --title "Add x" \
        --body-file body.txt --changed-files changed.txt

Rules:
- A PR into `develop` or an `umbrella/*` branch changes docs/STATUS.md, or its description
  has a line `STATUS.md: no change - <reason>`.
- A release PR (base `main`, title `Release <name>`) needs docs/STATUS.md to say
  `Cleaned for release: <name>`: the cleanup PR into `develop` comes first.
- docs/STATUS.md always has its required sections.
- PRs into any other base are not checked.
"""
import argparse
import re
import sys
from pathlib import Path

STATUS = "docs/STATUS.md"
SECTIONS = ("## Where we are", "## Done", "## In progress", "## Next", "## Open questions")
OPT_OUT = re.compile(r"^\s*STATUS\.md:\s*no change\s*[-–—:]\s*\S", re.IGNORECASE | re.MULTILINE)
RELEASE_TITLE = re.compile(r"^Release\s+(\S+)\s*$")
CLEANED = re.compile(r"Cleaned for release:\s*`?([^\s`]+)`?")


def check(base, title, body, changed, status_text):
    """Return a list of error messages; empty means the PR passes."""
    errors = []
    if status_text is None:
        return [f"{STATUS} is missing."]
    missing = [s for s in SECTIONS if not re.search(rf"^{re.escape(s)}\b", status_text, re.MULTILINE)]
    if missing:
        errors.append(f"{STATUS} is missing sections: {', '.join(missing)}.")

    if base == "main":
        m = RELEASE_TITLE.match(title.strip())
        if not m:
            errors.append("A PR into main is a release PR: its title must be `Release <name>`.")
            return errors
        name = m.group(1)
        cleaned = CLEANED.search(status_text)
        if not cleaned or cleaned.group(1) != name:
            found = cleaned.group(1) if cleaned else "nothing"
            errors.append(
                f"Release {name}: {STATUS} says `Cleaned for release: {found}`. Clean it up "
                f"in a PR into develop first and set `Cleaned for release: {name}` (AGENTS.md, Releases).")
        return errors

    if base == "develop" or base.startswith("umbrella/"):
        if STATUS not in changed and not OPT_OUT.search(body or ""):
            errors.append(
                f"Update {STATUS} with what this PR finishes or starts, or add a line "
                "`STATUS.md: no change - <reason>` to the PR description.")
    return errors


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", required=True, help="the PR's base branch")
    p.add_argument("--title", required=True)
    p.add_argument("--body-file", type=Path, help="file holding the PR description")
    p.add_argument("--changed-files", type=Path, required=True, help="one changed path per line")
    p.add_argument("--status", type=Path, default=Path(STATUS))
    a = p.parse_args(argv)
    body = a.body_file.read_text() if a.body_file and a.body_file.exists() else ""
    changed = {line.strip() for line in a.changed_files.read_text().splitlines() if line.strip()}
    status_text = a.status.read_text() if a.status.exists() else None
    errors = check(a.base, a.title, body, changed, status_text)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if not errors:
        print("STATUS.md check passed.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
