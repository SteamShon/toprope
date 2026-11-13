"""Pure evaluator for the check language."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from .ast import Arith, Call, Compare, ListLit, Literal, Logical, Neg, Node, Not, Path


class EvalError(ValueError):
    """A check could not be evaluated (type error, unknown root or function)."""


@dataclass
class Env:
    """Evaluation environment.

    `roots` maps root names (`target`, `actor`, `params`, ...) to values. Mappings and objects
    are both accepted: attribute access looks up a key first, then an attribute. `clock`
    supplies `now()`, so tests and the harness can use a virtual clock (docs/semantics.md §4).
    """

    roots: Mapping[str, Any]
    clock: Callable[[], datetime] | None = None
    functions: Mapping[str, Callable[..., Any]] = field(default_factory=dict)


def _get(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _as_utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _days_since(env: Env, t: Any) -> Any:
    if t is None:
        return None
    if env.clock is None:
        raise EvalError("days_since() needs a clock")
    if isinstance(t, str):
        try:
            t = datetime.fromisoformat(t)
        except ValueError as e:
            raise EvalError(f"days_since(): not an ISO datetime: {t!r}") from e
    elif isinstance(t, date) and not isinstance(t, datetime):
        t = datetime(t.year, t.month, t.day)
    if not isinstance(t, datetime):
        raise EvalError(f"days_since() expects a datetime, got {type(t).__name__}")
    # Naive times are UTC, so aware and naive values compare consistently.
    return (_as_utc(env.clock()) - _as_utc(t)).total_seconds() / 86400


def _call(node: Call, env: Env) -> Any:
    args = [evaluate(a, env) for a in node.args]
    match node.name, len(args):
        case "count", 1:
            v = args[0]
            if v is None:
                return 0
            if isinstance(v, (list, tuple, set, frozenset, Mapping, str)):
                return len(v)
            raise EvalError(f"count() expects a collection, got {type(v).__name__}")
        case "exists", 1:
            return args[0] is not None
        case "now", 0:
            if env.clock is None:
                raise EvalError("now() needs a clock")
            return env.clock()
        case "days_since", 1:
            return _days_since(env, args[0])
    if node.name in env.functions:
        return env.functions[node.name](*args)
    raise EvalError(f"unknown function {node.name}/{len(args)}")


_ORDER = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b}


def evaluate(node: Node, env: Env) -> Any:
    match node:
        case Literal(value):
            return value
        case ListLit(items):
            return [evaluate(i, env) for i in items]
        case Path(root, attrs):
            if root not in env.roots:
                raise EvalError(f"unknown root {root!r}")
            v = env.roots[root]
            for a in attrs:
                v = _get(v, a)
            return v
        case Call():
            return _call(node, env)
        case Not(operand):
            return not _truth(evaluate(operand, env))
        case Neg(operand):
            v = evaluate(operand, env)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise EvalError(f"cannot negate {type(v).__name__}")
            return -v
        case Logical("and", left, right):
            return _truth(evaluate(left, env)) and _truth(evaluate(right, env))
        case Logical("or", left, right):
            return _truth(evaluate(left, env)) or _truth(evaluate(right, env))
        case Arith(op, left, right):
            a, b = evaluate(left, env), evaluate(right, env)
            if op == "+" and (isinstance(a, str) or isinstance(b, str)):
                # String joining (ADR-0024): a string with a string or an integer. Floats,
                # booleans, null and lists fail closed, so no value is rendered ambiguously.
                if all(isinstance(x, str) or (isinstance(x, int) and not isinstance(x, bool)) for x in (a, b)):
                    return f"{a}{b}"
                raise EvalError(f"cannot join {type(a).__name__} and {type(b).__name__}")
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in (a, b)):
                raise EvalError(f"cannot apply {op} to {type(a).__name__} and {type(b).__name__}")
            return a + b if op == "+" else a - b if op == "-" else a * b
        case Compare(op, left, right):
            a, b = _times(evaluate(left, env), evaluate(right, env))
            if op == "==":
                return a == b
            if op == "!=":
                return a != b
            if op in ("in", "not_in"):
                # The right side must be a list. A null list is an error, not "empty", so a
                # missing list never silently allows (fail closed). Use count()/exists() to be explicit.
                if not isinstance(b, (list, tuple)):
                    raise EvalError(f"'{op.replace('_', ' ')}' expects a list, got {type(b).__name__}")
                found = a in b
                return found if op == "in" else not found
            if a is None or b is None:
                raise EvalError(f"cannot compare null with {op}")
            try:
                return _ORDER[op](a, b)
            except TypeError as e:
                raise EvalError(f"cannot compare {type(a).__name__} {op} {type(b).__name__}") from e
    raise EvalError(f"unknown node {node!r}")


def _times(a: Any, b: Any) -> tuple[Any, Any]:
    """Effects store datetimes as ISO strings, and `now()` is a datetime: when one side is a
    datetime, an ISO string on the other side is read as one. Anything else fails closed."""
    from datetime import datetime, timezone
    def parse(s: str) -> datetime:
        try:
            t = datetime.fromisoformat(s)
        except ValueError:
            raise EvalError(f"cannot compare a time with {s!r}") from None
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    if isinstance(a, datetime) and isinstance(b, str):
        return a, parse(b)
    if isinstance(b, datetime) and isinstance(a, str):
        return parse(a), b
    return a, b


def _truth(v: Any) -> bool:
    # Only booleans are truthy/falsy. Null is an error, so `not target.locked` on a missing
    # `locked` fails the check instead of allowing it (fail closed).
    if isinstance(v, bool):
        return v
    raise EvalError(f"expected a boolean, got {'null' if v is None else type(v).__name__}")
