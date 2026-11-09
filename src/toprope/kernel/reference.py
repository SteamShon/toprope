"""The kernel's command reference, generated from the commands' own argument parsers
(ADR-0037, resolved 3). The kernel is code, not a declaration, so its reference comes from its
code; each domain's own commands are in that domain's generated guide.

  python -m toprope.kernel.reference --out docs/kernel-commands.md
  python -m toprope.kernel.reference --check docs/kernel-commands.md   # exit 1 when stale
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path


def _commands() -> list[tuple[str, Callable[[], argparse.ArgumentParser], str]]:
    from ..adapters.cli import _base_parser
    from ..adapters.cli.change import build_parser as change
    from ..adapters.mcp.cli import build_parser as server
    from ..commits.cli import build_parser as commits
    from ..harness.cli import build_parser as harness
    from ..worldmap.cli import build_parser as worldmap
    return [
        ("toprope-run", lambda: _base_parser(add_help=True),
         "Its subcommands are the domain's actions, one per action, plus `get`, `history`, `allowed`, "
         "`whoami` and `guide`; each domain's guide lists them with who may take each."),
        ("toprope-change", change, ""),
        ("toprope-server", server, ""),
        ("toprope-harness", harness, ""),
        ("toprope-worldmap", worldmap, ""),
        ("toprope-commits", commits, ""),
    ]


def _actions(p: argparse.ArgumentParser) -> list[argparse.Action]:
    """A parser's arguments. argparse has no public way to list them, so this, and `_sub_help`,
    are the only places that read its internals; everything else goes by the arguments' public
    attributes, so a renamed private class changes nothing (#89)."""
    try:
        return list(p._actions)
    except AttributeError:
        raise RuntimeError("argparse no longer has ArgumentParser._actions: update "
                           "toprope.kernel.reference._actions") from None


def _sub_help(sp: argparse.Action) -> dict[str, str | None]:
    """Each subcommand's one-line help (`add_parser(help=...)`), which argparse keeps only on
    pseudo-actions. Empty when they are gone: the reference then shows no help line."""
    return {c.dest: c.help for c in getattr(sp, "_choices_actions", [])}


def _is_help(a: argparse.Action) -> bool:
    return a.nargs == 0 and "-h" in a.option_strings


def _is_subcommands(a: argparse.Action) -> bool:
    return isinstance(a.choices, dict) and bool(a.choices) and \
        all(isinstance(v, argparse.ArgumentParser) for v in a.choices.values())


def _cell(text: str) -> str:
    return " ".join(str(text or "").split()).replace("|", "\\|")


def _usage(a: argparse.Action) -> str:
    if not a.option_strings:
        return f"`{a.metavar or a.dest.upper()}`"
    flags = ", ".join(f"`{f}`" for f in a.option_strings)
    takes = a.nargs != 0
    if takes:
        meta = a.metavar or (a.dest.upper() if not a.choices else "{" + ",".join(map(str, a.choices)) + "}")
        flags += f" `{meta}`"
    return flags


def _options(p: argparse.ArgumentParser) -> list[str]:
    rows = []
    for a in _actions(p):
        if _is_help(a) or _is_subcommands(a):
            continue
        help_ = _cell(a.help)
        if a.required and a.option_strings:
            help_ = (help_ + " " if help_ else "") + "(required)"
        if a.default not in (None, False, argparse.SUPPRESS) and a.option_strings:
            help_ = (help_ + " " if help_ else "") + f"(default `{a.default}`)"
        rows.append(f"| {_usage(a)} | {help_} |")
    return (["| Argument | What |", "|---|---|"] + rows) if rows else []


def _summary(p: argparse.ArgumentParser) -> str:
    """The description's first paragraph, without the command name it starts with."""
    first = (p.description or "").strip().split("\n\n")[0]
    return " ".join(first.split())


def build_reference() -> str:
    out = ["# Kernel commands", "",
           "_Generated from the commands' argument parsers by `python -m toprope.kernel.reference`. "
           "Do not edit: change the parser, then regenerate._", "",
           "Link: none (an operating guide). These are the kernel's own commands (ADR-0027): the same "
           "for every domain. What a domain's people and agents do is in that domain's generated "
           "guide (`domains/<domain>/guide.md`). Run each as `uv run <command>` from the repository "
           "root.", ""]
    for name, make, note in _commands():
        p = make()
        out += [f"## `{name}`", "", _summary(p), ""]
        if note:
            out += [note, ""]
        out += _options(p) + [""]
        subs = [a for a in _actions(p) if _is_subcommands(a)]
        for sp in subs:
            helps = _sub_help(sp)
            for cmd, sub in sp.choices.items():
                out += [f"### `{name} {cmd}`", ""]
                if helps.get(cmd):
                    h = _cell(helps[cmd]).rstrip(".")
                    out += [h[:1].upper() + h[1:] + ".", ""]
                out += _options(sub) + [""]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m toprope.kernel.reference", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", help="write the reference to this file")
    g.add_argument("--check", help="exit 1 when this file differs from the generated reference")
    args = ap.parse_args(argv)
    text = build_reference()
    if args.out:
        Path(args.out).write_text(text)
        return
    if Path(args.check).read_text() != text:
        print(f"{args.check} is stale: run python -m toprope.kernel.reference --out {args.check}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
