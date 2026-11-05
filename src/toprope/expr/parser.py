"""Lexer and recursive-descent parser for the check language."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ast import Arith, Call, Compare, ListLit, Literal, Logical, Neg, Node, Not, Path

KEYWORDS = {"and", "or", "not", "in", "true", "false", "null"}

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
  | (?P<op>==|!=|<=|>=|<|>|\+|-|\(|\)|\[|\]|,|\.)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)


class ParseError(ValueError):
    def __init__(self, message: str, source: str, pos: int):
        super().__init__(f"{message} at column {pos + 1}: {source!r}")
        self.source = source
        self.pos = pos


@dataclass(frozen=True)
class Token:
    kind: str  # number | string | op | name | kw | eof
    text: str
    pos: int


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(source):
        m = _TOKEN.match(source, i)
        if not m:
            raise ParseError(f"unexpected character {source[i]!r}", source, i)
        kind = m.lastgroup
        text = m.group()
        if kind != "ws":
            if kind == "name" and text in KEYWORDS:
                kind = "kw"
            tokens.append(Token(kind, text, i))  # type: ignore[arg-type]
        i = m.end()
    tokens.append(Token("eof", "", len(source)))
    return tokens


def _unquote(text: str) -> str:
    body = text[1:-1]
    return re.sub(r"\\(.)", r"\1", body)


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.tokens = tokenize(source)
        self.i = 0

    # -- helpers -------------------------------------------------------------
    @property
    def tok(self) -> Token:
        return self.tokens[self.i]

    def peek(self, offset: int = 1) -> Token:
        return self.tokens[min(self.i + offset, len(self.tokens) - 1)]

    def accept(self, kind: str, text: str | None = None) -> Token | None:
        t = self.tok
        if t.kind == kind and (text is None or t.text == text):
            self.i += 1
            return t
        return None

    def expect(self, kind: str, text: str | None = None) -> Token:
        t = self.accept(kind, text)
        if t is None:
            want = text or kind
            raise ParseError(f"expected {want!r}, got {self.tok.text or 'end'!r}", self.source, self.tok.pos)
        return t

    # -- grammar -------------------------------------------------------------
    def parse(self) -> Node:
        node = self.or_expr()
        if self.tok.kind != "eof":
            raise ParseError(f"unexpected {self.tok.text!r}", self.source, self.tok.pos)
        return node

    def or_expr(self) -> Node:
        node = self.and_expr()
        while self.accept("kw", "or"):
            node = Logical("or", node, self.and_expr())
        return node

    def and_expr(self) -> Node:
        node = self.not_expr()
        while self.accept("kw", "and"):
            node = Logical("and", node, self.not_expr())
        return node

    def not_expr(self) -> Node:
        if self.tok.kind == "kw" and self.tok.text == "not" and not (
            self.peek().kind == "kw" and self.peek().text == "in"
        ):
            self.i += 1
            return Not(self.not_expr())
        return self.comparison()

    def comparison(self) -> Node:
        left = self.sum()
        t = self.tok
        if t.kind == "op" and t.text in ("==", "!=", "<", "<=", ">", ">="):
            self.i += 1
            return Compare(t.text, left, self.sum())
        if self.accept("kw", "in"):
            return Compare("in", left, self.sum())
        if t.kind == "kw" and t.text == "not" and self.peek().kind == "kw" and self.peek().text == "in":
            self.i += 2
            return Compare("not_in", left, self.sum())
        return left

    def sum(self) -> Node:
        node = self.unary()
        while self.tok.kind == "op" and self.tok.text in ("+", "-"):
            op = self.tok.text
            self.i += 1
            node = Arith(op, node, self.unary())
        return node

    def unary(self) -> Node:
        if self.accept("op", "-"):
            return Neg(self.unary())
        return self.postfix()

    def postfix(self) -> Node:
        node = self.primary()
        while self.accept("op", "."):
            name = self.expect("name")
            if not isinstance(node, Path):
                raise ParseError("attribute access is only allowed on paths", self.source, name.pos)
            node = Path(node.root, (*node.attrs, name.text))
        return node

    def primary(self) -> Node:
        t = self.tok
        if t.kind == "number":
            self.i += 1
            return Literal(float(t.text) if "." in t.text else int(t.text))
        if t.kind == "string":
            self.i += 1
            return Literal(_unquote(t.text))
        if t.kind == "kw" and t.text in ("true", "false", "null"):
            self.i += 1
            return Literal({"true": True, "false": False, "null": None}[t.text])
        if t.kind == "name":
            self.i += 1
            if self.accept("op", "("):
                args = self.arguments(")")
                return Call(t.text, tuple(args))
            return Path(t.text)
        if self.accept("op", "["):
            return ListLit(tuple(self.arguments("]")))
        if self.accept("op", "("):
            node = self.or_expr()
            self.expect("op", ")")
            return node
        raise ParseError(f"unexpected {t.text or 'end'!r}", self.source, t.pos)

    def arguments(self, close: str) -> list[Node]:
        args: list[Node] = []
        if self.accept("op", close):
            return args
        while True:
            args.append(self.or_expr())
            if self.accept("op", close):
                return args
            self.expect("op", ",")


def parse(source: str) -> Node:
    """Parse a check expression. Raises ParseError with the column on failure."""
    return _Parser(source).parse()
