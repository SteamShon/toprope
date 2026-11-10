"""Every error a person or an agent meets names its fix (ADR-0049, D1).

    raise AuthoringError(fixed(f"no source {sid!r}", "list the sources with `search_sources`"))

`tests/test_error_fixes.py` scans the modules on the change loop's path and fails on an error
raised with a message that does not go through `fixed`, and on a kernel service's `failure(…)`
reply without one.

What the scan cannot see: a message held in a variable (`raise E(msg)`), and the text of an error
passed on from a module outside the scan (`f"identity file: {e}"`, where `e` came from YAML or the
OS). Those are named here so they are not mistaken for covered. `docs/errors.md` is the catalog, generated
from the same scan (`python -m toprope.errors --out docs/errors.md`).
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

MARK = "Fix: "
# The modules whose errors reach a person or an agent in the change loop.
COVERED = (
    "adapters/cli/__init__.py",
    "adapters/cli/change.py",
    "adapters/cli/start.py",
    "adapters/mcp/cli.py",
    "commits/__init__.py",
    "identity/git.py",
    "kernel/services.py",
    "workspace/__init__.py",
)
# Exceptions whose message is shown as it is.
SHOWN = {"SystemExit", "ValueError", "RuntimeError", "KeyError", "AuthoringError", "CommitError",
         "MergeConflict", "FetchError"}
SRC = Path(__file__).resolve().parent


def fixed(message: str, fix: str) -> str:
    """`message`, then what to do about it."""
    message = message.rstrip().rstrip(":;,").rstrip()
    return f"{message}{'' if message.endswith(('.', '?', '!')) else '.'} {MARK}{fix}"


@dataclass(frozen=True)
class Raised:
    module: str
    line: int
    exception: str
    message: str          # the message as written, `{…}` where it is computed
    fix: str | None       # None: written without a fix


def _text(node: ast.AST) -> str | None:
    """The text of a string expression, with `{…}` for computed parts; None if not a string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{…}" for v in node.values)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"
            and (fmt := _text(node.func.value)) is not None):
        return fmt
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and (fmt := _text(node.left)) is not None:
        return fmt
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        if left is not None or right is not None:
            return (left or "{…}") + (right or "{…}")
    return None


def _passes_on(arg: ast.AST, caught: set[str]) -> bool:
    """A message that includes the error it caught (`f"people.{x}: {e}"`) passes that error's own
    message, and its fix, on."""
    return isinstance(arg, ast.JoinedStr) and any(
        isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name) and v.value.id in caught
        for v in arg.values)


def scan(src: Path = SRC, modules: tuple[str, ...] = COVERED) -> list[Raised]:
    """Every `raise E("…")` in the covered modules, with its fix if it has one. A raise that
    passes another error on (`str(e)`, or a message that includes it) or exits with a status is
    not a message of its own."""
    out = []
    for mod in modules:
        tree = ast.parse((src / mod).read_text())
        caught: dict[int, set[str]] = {}          # id(raise) -> names of the errors caught around it
        for h in ast.walk(tree):
            if isinstance(h, ast.ExceptHandler) and h.name:
                for n in ast.walk(h):
                    if isinstance(n, (ast.Raise, ast.Call)):
                        caught.setdefault(id(n), set()).add(h.name)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "failure" and node.args):
                call, name = node, "failure"              # a kernel service's failed reply
            elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                call = node.exc
                func = call.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name not in SHOWN or not call.args:
                    continue
            else:
                continue
            branches = [call.args[0]]
            while any(isinstance(b, ast.IfExp) for b in branches):   # either branch may be shown
                branches = [x for b in branches for x in ((b.body, b.orelse) if isinstance(b, ast.IfExp) else (b,))]
            for arg in branches:
                out += _one(mod, node, name, arg, caught.get(id(node), set()))
    return out


def _one(mod: str, node: ast.AST, name: str, arg: ast.AST, caught: set[str]) -> list[Raised]:
    if isinstance(arg, ast.Constant) and arg.value == "":      # an empty default, not a message
        return []
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "fixed" and len(arg.args) == 2:
        return [Raised(mod, node.lineno, name, _text(arg.args[0]) or "{…}", _text(arg.args[1]) or "{…}")]
    if _passes_on(arg, caught):
        return []
    text = _text(arg)
    return [] if text is None else [Raised(mod, node.lineno, name, text, None)]


def catalog(raised: list[Raised] | None = None) -> str:
    raised = scan() if raised is None else raised
    lines = ["# Errors and their fixes", "",
             "Link: none (generated by `python -m toprope.errors --out docs/errors.md`; ADR-0049, D1).",
             "Every error on the change loop's path, and what to do about it. `{…}` is filled in when",
             "the error is raised.", ""]
    for mod in sorted({r.module for r in raised}):
        lines += [f"## `{mod}`", "", "| Error | Fix |", "|---|---|"]
        for r in sorted((r for r in raised if r.module == mod), key=lambda r: (r.message, r.line)):
            cell = lambda s: s.replace("|", "\\|").replace("\n", " ")  # noqa: E731
            lines.append(f"| {cell(r.message)} | {cell(r.fix) if r.fix else '**none**'} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Write the error catalog.")
    ap.add_argument("--out", help="the file to write (default: print)")
    a = ap.parse_args(argv)
    text = catalog()
    if a.out:
        Path(a.out).write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
