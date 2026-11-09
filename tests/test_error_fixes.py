"""Every error on the change loop's path names its fix (ADR-0049, D1)."""
import ast
from pathlib import Path

import pytest

from toprope.errors import MARK, catalog, fixed, scan

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/errors.md"


def test_every_error_on_the_loops_path_names_its_fix():
    missing = [f"src/toprope/{r.module}:{r.line}: {r.message}" for r in scan() if r.fix is None]
    assert not missing, "errors without a fix; wrap the message as fixed(message, fix):\n" + "\n".join(missing)


def test_every_fix_says_something():
    empty = [f"src/toprope/{r.module}:{r.line}" for r in scan()
             if r.fix is not None and len(r.fix.replace("{…}", "").strip()) < 8]
    assert not empty, "a fix must say what to do, in words:\n" + "\n".join(empty)


def test_the_catalog_is_the_generated_one():
    assert DOC.read_text() == catalog(), \
        "docs/errors.md is stale: run python -m toprope.errors --out docs/errors.md"


def test_fixed_puts_the_fix_after_the_message():
    assert fixed("no source 'x'", "add it") == "no source 'x'. Fix: add it"
    assert fixed("nothing to check:", "commit first") == "nothing to check. Fix: commit first"
    assert MARK in fixed("a", "b")


def scan_text(tmp_path, code):
    (tmp_path / "m.py").write_text(code)
    return scan(tmp_path, ("m.py",))


def test_the_scan_finds_a_message_without_a_fix(tmp_path):
    r = scan_text(tmp_path, 'def f(x):\n    raise ValueError(f"no source {x!r}")\n')
    assert [(r0.line, r0.message, r0.fix) for r0 in r] == [(2, "no source {…}", None)]


def test_the_scan_reads_the_fix_and_skips_what_passes_an_error_on(tmp_path):
    r = scan_text(tmp_path, (
        'def f(x):\n'
        '    try:\n'
        '        g()\n'
        '    except ValueError as e:\n'
        '        raise SystemExit(f"identity file: {e}") from None\n'
        '    raise SystemExit(1)\n'
        'def h():\n'
        '    raise KeyError(fixed("no service", "use one listed"))\n'))
    assert [(r0.message, r0.fix) for r0 in r] == [("no service", "use one listed")]


def test_the_scan_covers_a_message_built_with_plus(tmp_path):
    r = scan_text(tmp_path, 'def f(x):\n    raise RuntimeError("a " + x + " b")\n')
    assert r[0].message == "a {…} b" and r[0].fix is None


def test_each_branch_of_a_conditional_message_needs_a_fix(tmp_path):
    r = scan_text(tmp_path, 'def f(x):\n    raise SystemExit(x() if x else "no caller")\n')
    assert [(r0.message, r0.fix) for r0 in r] == [("no caller", None)]


def test_format_and_percent_messages_are_scanned(tmp_path):
    r = scan_text(tmp_path, ('def f(x):\n    raise ValueError("no {}".format(x))\n'
                             'def g(x):\n    raise ValueError("no %s" % x)\n'))
    assert sorted(r0.message for r0 in r) == ["no %s", "no {}"]


def test_a_services_failure_reply_is_scanned_and_its_empty_default_is_not(tmp_path):
    r = scan_text(tmp_path, ('def f(svc, x):\n    svc.failure("")\n'
                             '    return svc.failure(f"missing inputs {x}")\n'))
    assert [(r0.exception, r0.message, r0.fix) for r0 in r] == [("failure", "missing inputs {…}", None)]


def test_a_merge_conflict_names_its_fix():
    from toprope.commits import Conflict, MergeConflict
    assert MARK in str(MergeConflict([Conflict("actions.a", None, 1, 2)]))
