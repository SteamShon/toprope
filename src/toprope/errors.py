"""Every error a person or an agent meets names its fix (ADR-0049, D1; ADR-0053 §5).

    raise AuthoringError(fixed(f"no source {sid!r}", "list the sources with `search_sources`"))

`tests/test_error_fixes.py` scans every module of `src/toprope/` and `tools/human_request.py`, and
fails on an error raised with a message that does not go through `fixed` (a `DeployRefused`'s
reason included), on a kernel service's `failure(…)` reply without one, on a reply's `error` or
`reason` text without one, on a command's refusal (`Outcome("denied" | "rejected", code, reason)`,
the interpreter's `deny`/`_attempt`, a reason a gate function returns) without one, and on a message
with two `Fix:` parts.

The scan is static. What it cannot see: a message held in a variable (`raise E(msg)`, `reason =
…`), a message built by a call it does not read (`"; ".join(errors)`), an exception type it does not
list, and the text of an error passed on from a module outside the scan (`f"identity file: {e}"`,
where `e` came from YAML or the OS); at run time, a passed-on message may hold its own fix, which
`fixed` merges into one. Those are named here so they are not mistaken for covered. `docs/errors.md` is the catalog, generated
from the same scan (`python -m toprope.errors --out docs/errors.md`).
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

MARK = "Fix: "
SRC = Path(__file__).resolve().parent
ROOT = SRC.parents[1]                   # the repository, when the package runs from its checkout
# Every module of the package, and the tool that runs a person's approved steps (ADR-0039).
TOOLS = ("tools/human_request.py",)


def covered(root: Path = ROOT) -> tuple[str, ...]:
    """The scanned files, relative to `root`. No module is left out."""
    mods = sorted(str(p.relative_to(root)) for p in (root / "src" / "toprope").rglob("*.py"))
    return tuple(mods) + tuple(t for t in TOOLS if (root / t).is_file())


# Exceptions whose message is shown as it is.
SHOWN = {"SystemExit", "ValueError", "RuntimeError", "KeyError", "AuthoringError", "CommitError",
         "MergeConflict", "FetchError", "ToolError"}
# Exceptions whose message is not their first argument: the position of the one shown.
SHOWN_AT = {"DeployRefused": 1}
# A reply's keys that hold a message shown to its caller (`{"error": "…"}`, `{"reason": "…"}`).
REPLY_KEYS = ("error", "reason")
TYPE_NAMES = {"string", "strings", "boolean", "integer", "number", "datetime"}   # a schema's dict, not a reply
# A command's refusal: the call, and the position of its reason. `Outcome` counts only when its
# status is "denied" or "rejected".
REFUSALS = {"Outcome": 2, "deny": 1, "_attempt": 3}
# Functions whose returned text (`return "…"`, `return False, "…"`) is a refusal's reason.
REASONS = {"actor_allowed", "invalid_params", "_moved_since", "no_action"}
REASON_MODULES = ("src/toprope/semantics/refusals.py",)   # every function there returns a reason


def fixed(message: str, fix: str, *, verbatim: bool = False) -> str:
    """`message`, then what to do about it.

    Our own message may pass on another's that already names a fix (a failed step's): it keeps one
    `Fix:` part, every fix it held first, then `fix`, each once; so `fixed(fixed(m, f), f)` is
    `fixed(m, f)`. With `verbatim`, the message is someone else's words (a domain's declared
    reason): it is kept exactly, `Fix:` in it included, and `fix` follows it."""
    if verbatim:
        return f"{message} {MARK}{fix}"
    if MARK in message:
        kept, before = [], []
        for line in message.split("\n"):             # a fix runs to the end of its line
            head, *fs = line.split(MARK)
            kept.append(head)
            before += fs
        message = "\n".join(k for k in kept if k.strip())
        fixes: list[str] = []
        for f in [*before, fix]:
            f = f.strip().rstrip(".;").strip()
            if f and f not in fixes:
                fixes.append(f)
        fix = "; then ".join(fixes)
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
        return "".join(v.value if isinstance(v, ast.Constant)
                       else v.value.value if (isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Constant)
                                              and isinstance(v.value.value, str) and v.conversion == -1
                                              and v.format_spec is None)
                       else "{…}" for v in node.values)
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
    def caught_name(x: ast.AST) -> bool:      # `e`, or a part of it (`e.reason`)
        while isinstance(x, ast.Attribute):
            x = x.value
        return isinstance(x, ast.Name) and x.id in caught
    return isinstance(arg, ast.JoinedStr) and any(
        isinstance(v, ast.FormattedValue) and caught_name(v.value) for v in arg.values)


def _call_name(call: ast.Call) -> str | None:
    return call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", None)


def _message_of(node: ast.AST) -> tuple[ast.AST, str] | None:
    """The message a node shows and what shows it, if it shows one."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "failure" and node.args):
        return node.args[0], "failure"                   # a kernel service's failed reply
    if isinstance(node, ast.Call) and (name := _call_name(node)) in REFUSALS:
        k = REFUSALS[name]
        if len(node.args) <= k:
            return None
        if name == "Outcome" and not (isinstance(node.args[0], ast.Constant)
                                      and node.args[0].value in ("denied", "rejected")):
            return None
        return node.args[k], name                        # a command's refusal
    if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
        name = _call_name(node.exc)
        if name in SHOWN and node.exc.args:
            return node.exc.args[0], name
        if name in SHOWN_AT and len(node.exc.args) > SHOWN_AT[name]:
            return node.exc.args[SHOWN_AT[name]], name
    return None


def _replies(tree: ast.AST) -> list[tuple[ast.Dict, ast.AST]]:
    """The messages replies carry: `{"error": "…"}`, `{"reason": "…"}`."""
    return [(n, v) for n in ast.walk(tree) if isinstance(n, ast.Dict)
            and not all(isinstance(x, ast.Constant) and x.value in TYPE_NAMES
                        for k, x in zip(n.keys, n.values) if k is not None)
            for k, v in zip(n.keys, n.values)
            if isinstance(k, ast.Constant) and k.value in REPLY_KEYS]


def _returned(tree: ast.AST, every: bool = False) -> list[tuple[ast.Return, ast.AST]]:
    """The reasons the gate functions return (every public function's, with `every`): `return "…"`
    and `return False, "…"`."""
    out = []
    for f in ast.walk(tree):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                f.name in REASONS or (every and not f.name.startswith("_"))):
            for r in ast.walk(f):
                if not isinstance(r, ast.Return) or r.value is None:
                    continue
                v = r.value
                if isinstance(v, ast.Tuple) and len(v.elts) == 2:
                    v = v.elts[1]
                out.append((r, v))
    return out


class _Inline(ast.NodeTransformer):
    """A module's string constants (`ASK = "…"`), read in place where a message uses them."""

    def __init__(self, tree: ast.Module):
        self.text: dict[str, str] = {}
        for n in tree.body:                       # in order, so a constant may use one above it
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(t := n.targets[0], ast.Name):
                if (s := _text(self.visit(n.value))) is not None:
                    self.text[t.id] = s

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, ast.Load) and node.id in self.text:
            return ast.copy_location(ast.Constant(self.text[node.id]), node)
        return node


def _passers(tree: ast.AST) -> dict[str, tuple[int, int, ast.AST]]:
    """Functions such as `stop(i, message, fix)` that raise `fixed(… message …, fix)` with their
    parameters: name -> (position of the message, position of the fix, the function)."""
    out = {}
    for f in ast.walk(tree):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = [a.arg for a in f.args.args]
        for c in ast.walk(f):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "fixed"
                    and len(c.args) == 2 and isinstance(c.args[1], ast.Name) and c.args[1].id in params):
                used = [n.id for n in ast.walk(c.args[0]) if isinstance(n, ast.Name) and n.id in params]
                if used:
                    out[f.name] = (params.index(used[-1]), params.index(c.args[1].id), f)   # the last: the message itself
    return out


def scan(src: Path = ROOT, modules: tuple[str, ...] | None = None) -> list[Raised]:
    """Every `raise E("…")`, service failure and command refusal in the scanned files, with its fix
    if it has one. A raise that passes another error on (`str(e)`, or a message that includes it)
    or exits with a status is not a message of its own."""
    out = []
    for mod in covered(src) if modules is None else modules:
        tree = ast.parse((src / mod).read_text())
        tree = _Inline(tree).visit(tree)
        caught: dict[int, set[str]] = {}          # id(raise) -> names of the errors caught around it
        for h in ast.walk(tree):
            if isinstance(h, ast.ExceptHandler) and h.name:
                for n in ast.walk(h):
                    if isinstance(n, (ast.Raise, ast.Call, ast.Return, ast.Dict)):
                        caught.setdefault(id(n), set()).add(h.name)
        passed = _passers(tree)                    # functions that raise with a fix their caller gives
        inside = {id(n) for f in passed.values() for n in ast.walk(f[2])}
        found = [(node, *m) for node in ast.walk(tree)
                 if id(node) not in inside and (m := _message_of(node)) is not None]
        for node in ast.walk(tree):                # their calls carry the message and its fix
            if isinstance(node, ast.Call) and (p := passed.get(_call_name(node) or "")) and len(node.args) > p[1]:
                out.append(Raised(mod, node.lineno, _call_name(node), _text(node.args[p[0]]) or "{…}",
                                  _text(node.args[p[1]]) or "{…}"))
        found += [(r, v, "refusal") for r, v in _returned(tree, mod in REASON_MODULES)]
        found += [(r, v, "reply") for r, v in _replies(tree)]
        for node, first, name in found:
            branches = [first]
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
             "Every error, refusal and failed reply the kernel, the CLI and the request runner show, and what",
             "to do about it. `{…}` is filled in when the error is raised.", ""]
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
