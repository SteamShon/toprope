"""Every error on the change loop's path names its fix (ADR-0049, D1)."""
import ast
from pathlib import Path

import pytest

from toprope.errors import MARK, ROOT as SCANNED, catalog, covered, fixed, scan

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/errors.md"


def test_every_error_names_its_fix():
    missing = [f"{r.module}:{r.line}: {r.message}" for r in scan() if r.fix is None]
    assert not missing, "errors without a fix; wrap the message as fixed(message, fix):\n" + "\n".join(missing)


def test_the_scan_covers_the_whole_package_and_the_request_runner():
    assert SCANNED == ROOT
    every = {str(p.relative_to(ROOT)) for p in (ROOT / "src/toprope").rglob("*.py")} | {"tools/human_request.py"}
    assert set(covered()) == every


def test_no_message_names_two_fixes():
    two = [f"{r.module}:{r.line}: {r.message}" for r in scan()
           if MARK in r.message or (r.fix is not None and MARK in r.fix)]
    assert not two, "a message with two `Fix:` parts; give fixed() the message without its own fix:\n" + "\n".join(two)


def test_every_fix_says_something():
    empty = [f"{r.module}:{r.line}" for r in scan()
             if r.fix is not None and len(r.fix.replace("{…}", "").strip()) < 8]
    assert not empty, "a fix must say what to do, in words:\n" + "\n".join(empty)


def test_the_catalog_is_the_generated_one():
    assert DOC.read_text() == catalog(), \
        "docs/errors.md is stale: run python -m toprope.errors --out docs/errors.md"


def test_fixed_puts_the_fix_after_the_message():
    assert fixed("no source 'x'", "add it") == "no source 'x'. Fix: add it"
    assert fixed("nothing to check:", "commit first") == "nothing to check. Fix: commit first"
    assert MARK in fixed("a", "b")


def test_fixed_keeps_one_fix_when_the_message_names_its_own():
    assert fixed("step 2 failed: no chunk 'x'. Fix: run `search`.", "run the step again") == \
        "step 2 failed: no chunk 'x'. Fix: run `search`; then run the step again"


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


def test_the_scan_finds_a_refusal_without_a_fix(tmp_path):
    r = scan_text(tmp_path, (
        'def decide(self, cmd):\n'
        '    if cmd: return Outcome("rejected", "unknown-action", f"No action {cmd}.")\n'
        '    if self: return deny("undecided", "Undecided.")\n'
        '    if cmd is None: return self._attempt(cmd, "O", "actor", "Nobody may.", None)\n'
        '    return Outcome("ok", state={})\n'
        'def actor_allowed(self, action, cmd, view):\n'
        '    if action: return False, f"Only a person can {cmd}."\n'
        '    return True, ""\n'
        'def invalid_params(action, params):\n'
        '    return f"Missing param {params}."\n'))
    assert sorted((r0.exception, r0.message, r0.fix) for r0 in r) == [
        ("Outcome", "No action {…}.", None), ("_attempt", "Nobody may.", None), ("deny", "Undecided.", None),
        ("refusal", "Missing param {…}.", None), ("refusal", "Only a person can {…}.", None)]


def test_the_scan_reads_a_fix_held_in_a_module_constant(tmp_path):
    r = scan_text(tmp_path, ('VIA = "on a terminal"\nASK = f"ask a person: {VIA}"\n'
                             'def f(a):\n    raise ValueError(fixed(f"only a person can {a}", ASK))\n'))
    assert [(r0.message, r0.fix) for r0 in r] == [("only a person can {…}", "ask a person: on a terminal")]


def test_a_merge_conflict_names_its_fix():
    from toprope.commits import Conflict, MergeConflict
    assert MARK in str(MergeConflict([Conflict("actions.a", None, 1, 2)]))


# -- the gate refusals agents meet most: each names what to do (ADR-0049 §5) -------------------
def gate_refusals():
    """One refusal of each kind the interpreter gives, on the schema doc's domain."""
    from datetime import timedelta

    from test_semantics import ANA, BOT, ELI, NOW, PAT, do, model
    from toprope.semantics import Actor, Command, Grant

    def human(raw):
        raw["actions"]["approve_experiment"]["requires"] = "human"

    def skip_approval(raw):
        raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"

    def creates_effect(raw):
        raw["actions"]["approve_experiment"]["effects"].append({"create": "Readout"})

    m = model()
    m.seed("Experiment", {"id": "E-run", "status": "running", "approved_by": "ana", "started_at": "x"})
    m.seed("Experiment", {"id": "E-end", "status": "ended", "approved_by": "ana", "started_at": "x"})
    g = Grant("g1", frozenset({"approve_experiment"}), expires_at=NOW + timedelta(hours=1))
    return {
        "requires-human": do(model(human), BOT, "approve_experiment", "E-onboarding", on_behalf_of=ANA, grant=g),
        "role": do(m, ELI, "approve_experiment", "E-onboarding"),
        "no-grant": do(m, BOT, "approve_experiment", "E-onboarding"),
        "grant-scope": do(m, BOT, "approve_experiment", "E-onboarding", on_behalf_of=ANA,
                          grant=Grant("g2", frozenset({"launch_experiment"}))),
        "grant-expired": do(m, BOT, "approve_experiment", "E-onboarding", on_behalf_of=ANA,
                            grant=Grant("g0", frozenset({"approve_experiment"}), expires_at=NOW)),
        "principal-role": do(m, BOT, "approve_experiment", "E-onboarding", on_behalf_of=PAT, grant=g),
        "principal-kind": do(m, BOT, "approve_experiment", "E-onboarding",
                             on_behalf_of=Actor("root", "system", ("approver",)), grant=g),
        "matrix": do(m, ELI, "launch_experiment", "E-onboarding"),
        "not-applicable": do(m, ELI, "launch_experiment", "E-run"),
        "undecided": do(m, ELI, "launch_experiment", "E-end"),
        "precondition": do(m, ANA, "approve_experiment", "E-bare"),
        "invariant": do(model(skip_approval), ELI, "launch_experiment", "E-onboarding"),
        "unknown-actor": m.execute(Command(None, "approve_experiment", "E-onboarding")),
        "unknown-action": do(m, ANA, "nope", "E-onboarding"),
        "not-found": do(m, ANA, "approve_experiment", "E-ghost"),
        "no-target": m.execute(Command(ANA, "approve_experiment", None)),
        "bad-param": do(m, ANA, "approve_experiment", "E-onboarding", params={"note": 3}),
        "unknown-param": do(m, ANA, "approve_experiment", "E-onboarding", params={"bogus": 1}),
        "unsupported-effect": do(model(creates_effect), ANA, "approve_experiment", "E-onboarding"),
    }


def test_every_gate_refusal_names_one_fix():
    out = gate_refusals()
    assert all(o.status in ("denied", "rejected") for o in out.values()), out
    bad = {k: o.reason for k, o in out.items() if (o.reason or "").count(MARK) != 1}
    assert not bad, f"refusals without exactly one fix: {bad}"


def test_a_refusal_only_a_person_can_resolve_names_the_human_request():
    out = gate_refusals()
    for k in ("requires-human", "role", "principal-role", "grant-scope"):
        fix = out[k].reason.split(MARK, 1)[1]
        assert "ask a person" in fix and "human request" in fix and "toprope-change" in fix, (k, fix)
    assert out["requires-human"].reason.startswith("Only a person can approve_experiment. Fix: ask a person")


def test_a_declared_reason_stays_the_domains_words_and_gains_a_generic_fix():
    from test_semantics import domain
    d = domain()
    out = gate_refusals()
    pre = next(p for p in d.actions["approve_experiment"].preconditions if p.id == out["precondition"].code)
    assert out["precondition"].reason == \
        f"{pre.reason} Fix: the action is allowed when `{pre.check}`; change the object or the params first"
    deny = d.transitions["Experiment"].matrix["draft"]["launch_experiment"].deny
    assert out["matrix"].reason == (f"{deny} Fix: launch_experiment is denied when the Experiment is draft; it applies "
                                    "when the Experiment is approved")
    assert out["not-applicable"].reason.startswith("Not applicable when running. Fix: launch_experiment applies when "
                                                   "the Experiment is approved")
