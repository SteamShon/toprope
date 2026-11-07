"""Check that a PR only extends the self domains' append-only logs (AGENTS.md, "Self domains").

The self domains' commit store (`.toprope/commits/<domain>/*.jsonl`) and their event logs and
interview logs (`domains/<domain>/**/*.jsonl`) advance on one line only. Two branches that each
ran the loop from the same point both write a commit with the same sequence number and both
move `main`; git then sees only a conflict at the end of a file, and joining the lines would
give duplicate sequence numbers and a `main` decided by line order (#124's review). So every
such file at the PR's head must start with the file as it is at the base.

    python tools/logs_check.py --base origin/develop [--head HEAD]
"""
from __future__ import annotations

import argparse
import subprocess
import sys

PATTERNS = (".toprope/commits/*/*.jsonl", "domains/*/*.jsonl", "domains/*/events/*.jsonl")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def files(rev: str) -> set[str]:
    out = _git("ls-tree", "-r", "--name-only", rev, "--", ".toprope/commits", "domains")
    import fnmatch
    return {p for p in out.stdout.splitlines() if any(fnmatch.fnmatch(p, pat) for pat in PATTERNS)}


def show(rev: str, path: str) -> str | None:
    r = _git("show", f"{rev}:{path}")
    return r.stdout if r.returncode == 0 else None


def check(base: str, head: str = "HEAD") -> list[str]:
    errors = []
    for path in sorted(files(base)):
        before, after = show(base, path), show(head, path)
        if after is None:
            errors.append(f"{path}: removed; an append-only log is never removed")
        elif not after.startswith(before):
            n = next((i for i, (a, b) in enumerate(zip(before.splitlines(), after.splitlines())) if a != b),
                     min(len(before.splitlines()), len(after.splitlines())))
            errors.append(f"{path}: line {n + 1} differs from the base's; the self domains' logs only "
                          "grow. Take the base's file and run the loop again from it (AGENTS.md, Self domains)")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="the base revision, e.g. origin/develop")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args(argv)
    errors = check(a.base, a.head)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    print("self-domain logs only extend." if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
