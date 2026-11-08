"""What an agent in an arm may see (run protocol §1, "No experiment words").

No directory, file, prompt or tool name an agent sees may contain an experiment word. Words a
domain's own declarations and tools use stay as they are, so the domain's content is not checked:
the harness's own text is (its prompts, the arms' descriptions, its tools' names and
descriptions, the names of the files in a workspace). A tool never shows an agent the absolute
path of its workspace either, since that path runs through the repository's experiment
directories: it is replaced with `.` in every result and error.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# The protocol's list. Whole words, any case; `arm` also as `arms`, `eval` also as `evaluate` etc.
WORDS = ("experiment", "eval", "arm", "seeded", "answer key", "change key", "judge", "score",
         "benchmark", "recall", "M1")
_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(experiments?|eval\w*|arms?|seeded|answer[ _-]keys?|change[ _-]keys?|judge\w*|"
    r"scor\w*|benchmarks?|recall\w*|m1)(?![A-Za-z0-9])", re.IGNORECASE)


class BlindError(RuntimeError):
    """The harness was about to show an agent an experiment word."""


def words_in(text: str) -> list[str]:
    return sorted({m.group(0) for m in _PATTERN.finditer(text)})


def check(where: str, text: str) -> None:
    found = words_in(text)
    if found:
        raise BlindError(f"{where} would show an agent {found} (run protocol §1): rename it")


def check_tools(tools: list[Any]) -> None:
    for t in tools:
        check(f"tool {t.name!r}", f"{t.name}\n{t.description}")


def check_files(root: Path) -> None:
    """The names of the files an agent's file tools list."""
    for p in sorted(root.rglob("*")):
        check(f"file {p.relative_to(root)}", str(p.relative_to(root)))


def redact(value: Any, root: Path) -> Any:
    """`value` with the workspace's absolute path (resolved or as given) replaced by `.`."""
    paths = sorted({str(root), str(root.resolve())}, key=len, reverse=True)

    def one(s: str) -> str:
        for p in paths:
            s = s.replace(p, ".")
        return s

    if isinstance(value, str):
        return one(value)
    if isinstance(value, dict):
        return {redact(k, root): redact(v, root) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, root) for v in value]
    return value
