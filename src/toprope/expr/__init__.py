"""The `check` expression language (docs/domain-schema.md, ADR-0010).

Grammar (lowest to highest precedence)::

    expr       := or_expr
    or_expr    := and_expr ("or" and_expr)*
    and_expr   := not_expr ("and" not_expr)*
    not_expr   := "not" not_expr | comparison
    comparison := sum (("==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "not" "in") sum)?
    sum        := unary (("+" | "-") unary)*
    unary      := "-" unary | postfix
    postfix    := primary ("." NAME)*
    primary    := NUMBER | STRING | "true" | "false" | "null" | NAME
                | NAME "(" [expr ("," expr)*] ")" | "[" [expr ("," expr)*] "]" | "(" expr ")"

Paths start at a root name (`target`, `actor`, `params`, `new`). A missing attribute
evaluates to `null`. Functions: `count(x)`, `exists(x)`, `now()`, `days_since(t)`.
Evaluation is pure and never calls into Python's `eval`.

Fail closed: `and`/`or`/`not` accept only booleans (null is an error), `in`/`not in` need a
list on the right (a null list is an error), and type errors raise `EvalError`. Callers
treat a check that raises as failed.
"""

from .ast import Call, Compare, ListLit, Literal, Logical, Not, Path, Arith, Neg, Node
from .parser import ParseError, parse
from .eval import EvalError, Env, evaluate
from .deps import paths_read

__all__ = [
    "Arith", "Call", "Compare", "Env", "EvalError", "ListLit", "Literal", "Logical", "Neg",
    "Node", "Not", "ParseError", "Path", "evaluate", "parse", "paths_read",
]
