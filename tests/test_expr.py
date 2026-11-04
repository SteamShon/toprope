from datetime import datetime, timedelta

import pytest
from hypothesis import given, strategies as st

from toprope.expr import Env, EvalError, ParseError, Path, evaluate, parse, paths_read

T = {"status": "running", "guardrails": ["m1"], "approved_by": "ana", "planned_days": 14,
     "started_at": "2026-11-01T00:00:00", "owner": "pat"}
CLOCK = lambda: datetime(2026, 11, 20)  # noqa: E731


def ev(src, target=T, **roots):
    return evaluate(parse(src), Env({"target": target, "actor": {"id": "ana", "role": "approver"},
                                     "params": {}, **roots}, clock=CLOCK))


@pytest.mark.parametrize("src, expected", [
    ("target.status == 'running'", True),
    ('target.status != "draft"', True),
    ("count(target.guardrails) >= 1", True),
    ("count(target.missing) == 0", True),
    ("exists(target.approved_by)", True),
    ("exists(target.nope)", False),
    ("target.status in ['running', 'ended']", True),
    ("target.status not in ['running', 'ended', 'decided'] or exists(target.approved_by)", True),
    ("not (target.status == 'draft')", True),
    ("target.planned_days - 7 >= 7", True),
    ("-target.planned_days < 0", True),
    ("days_since(target.started_at) >= target.planned_days", True),
    ("actor.id == target.owner", False),
    ("target.a.b.c == null", True),
    ("true and not false", True),
    ("1 + 2 == 3 and 2.5 > 2", True),
])
def test_evaluates(src, expected):
    assert ev(src) is expected


def test_invariant_shape_from_schema_doc():
    inv = "target.status not in ['running', 'ended', 'decided'] or exists(target.approved_by)"
    assert ev(inv, {"status": "draft"}) is True
    assert ev(inv, {"status": "running"}) is False
    assert ev(inv, {"status": "running", "approved_by": "ana"}) is True


@pytest.mark.parametrize("src", [
    "target.planned_days > 'x'",      # type error
    "target.nope < 3",                # null ordering
    "count(target.planned_days)",     # count of a number
    "unknown_root.x == 1",
    "frobnicate(1)",
    "target.status and true",         # non-boolean in logic
    "'a' in target.planned_days",
])
def test_eval_errors_fail_closed(src):
    with pytest.raises(EvalError):
        ev(src)


def test_now_requires_clock():
    with pytest.raises(EvalError):
        evaluate(parse("now() == null"), Env({"target": {}}))


@pytest.mark.parametrize("src", [
    "target.", "a ==", "(a == 1", "a == 1)", "[1, 2", "a = 1", "a.b(", "1.x", "'unterminated", "a $ b",
])
def test_parse_errors_report_column(src):
    with pytest.raises(ParseError) as e:
        parse(src)
    assert "column" in str(e.value)


def test_paths_read():
    node = parse("count(target.guardrails) >= 1 and actor.role in params.roles or target.x.y == 1")
    assert {p.dotted() for p in paths_read(node)} == {
        "target.guardrails", "actor.role", "params.roles", "target.x.y"}
    assert Path("target", ("guardrails",)) in paths_read(node)


def test_custom_function_port():
    env = Env({"target": {"n": 4}}, functions={"double": lambda x: x * 2})
    assert evaluate(parse("double(target.n) == 8"), env) is True


@given(st.text(max_size=40))
def test_parser_only_raises_parse_error(s):
    try:
        parse(s)
    except ParseError:
        pass


@given(st.integers(-10**6, 10**6), st.integers(-10**6, 10**6))
def test_arithmetic_and_order_match_python(a, b):
    assert ev(f"{a} - {b} < {b}") is (a - b < b)
    assert ev(f"{a} + {b} >= {a}") is (a + b >= a)
