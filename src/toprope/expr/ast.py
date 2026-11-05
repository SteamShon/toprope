"""AST nodes for the check language. Immutable, hashable, comparable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class Node:
    """Base class for expression nodes."""


@dataclass(frozen=True)
class Literal(Node):
    value: Any  # int | float | str | bool | None


@dataclass(frozen=True)
class ListLit(Node):
    items: tuple[Node, ...]


@dataclass(frozen=True)
class Path(Node):
    root: str
    attrs: tuple[str, ...] = ()

    def dotted(self) -> str:
        return ".".join((self.root, *self.attrs))


@dataclass(frozen=True)
class Call(Node):
    name: str
    args: tuple[Node, ...]


@dataclass(frozen=True)
class Not(Node):
    operand: Node


@dataclass(frozen=True)
class Neg(Node):
    operand: Node


@dataclass(frozen=True)
class Logical(Node):
    op: str  # "and" | "or"
    left: Node
    right: Node


@dataclass(frozen=True)
class Compare(Node):
    op: str  # == != < <= > >= in not_in
    left: Node
    right: Node


@dataclass(frozen=True)
class Arith(Node):
    op: str  # + -
    left: Node
    right: Node
