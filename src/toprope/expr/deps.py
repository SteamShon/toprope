"""Dependency extraction: which paths does an expression read? (ADR-0013)"""

from __future__ import annotations

from .ast import Arith, Call, Compare, ListLit, Literal, Logical, Neg, Node, Not, Path


def paths_read(node: Node) -> set[Path]:
    """Every path the expression reads, as written. Linked objects are resolved by the caller
    against the declaration (a path through a link depends on the link and its target type)."""
    out: set[Path] = set()

    def walk(n: Node) -> None:
        match n:
            case Path():
                out.add(n)
            case Literal():
                pass
            case ListLit(items):
                for i in items:
                    walk(i)
            case Call(_, args):
                for a in args:
                    walk(a)
            case Not(o) | Neg(o):
                walk(o)
            case Logical(_, a, b) | Compare(_, a, b) | Arith(_, a, b):
                walk(a)
                walk(b)

    walk(node)
    return out
