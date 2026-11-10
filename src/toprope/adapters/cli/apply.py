"""`toprope-apply`: a person applies a human request at their own terminal, with one
confirmation (ADR-0053, 3; ADR-0039 without GitHub).

    toprope-apply .toprope/requests/<id>.yaml [--ship]

It shows the request as the `human-request` workflow's run page does (every step, the risk and its
reasons, the diff a confirm step confirms), asks you to type `yes` once, then runs the steps as you
(your git email, looked up in `toprope.identity.yaml`, as `toprope-run` resolves you), records the
run in `.toprope/approval-runs.jsonl` with `channel: local`, and removes the request. F1 counts it
as one approval, like an approved run in GitHub. A step that fails stops it; the steps before it
keep their work and the request keeps the steps that are left, to apply again once fixed.

It refuses without a terminal, and for a caller who is not a person (an agent's own git email).
A commit not recorded low risk is not put in use on the same confirmation: the run stops after
its preview, and you apply the request again once you have read it (ADR-0050, 3). `--ship` adds
the delivery steps to a request that approves the commit it makes, so a high-risk change takes
two confirmations in all.

The one confirmation stands for each person-only step's own terminal prompt: `toprope-apply`
gives its steps a token that `toprope-run` accepts in place of asking again, only from the process
that took the confirmation, and only for the person who gave it. Like that prompt, it guards
against mistakes; it is not a security boundary (a process can fake a terminal).

Run it from the repository root: the request runner is the repository's `tools/human_request.py`.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.util
import json
import os
import secrets
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from ...errors import fixed

APPLY_ENV = "TOPROPE_APPLY"          # the confirmation `toprope-apply` took, for the steps it runs
RUNNER = "tools/human_request.py"


def _dir() -> Path:
    try:
        user = getpass.getuser()
    except (KeyError, OSError):         # no user name in this environment
        user = str(os.getuid()) if hasattr(os, "getuid") else "user"
    return Path(tempfile.gettempdir()) / f"toprope-apply-{user}"


def _file(token: str) -> Path:
    return _dir() / f"{hashlib.sha256(token.encode()).hexdigest()}.json"


@contextmanager
def confirmation(person: str) -> Iterator[str]:
    """A token for the steps of one confirmed apply: it names the person who confirmed and the
    process that asked them, and it is gone when the apply ends. Kept outside the repository."""
    token = secrets.token_hex(16)
    _dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    f = _file(token)
    f.write_text(json.dumps({"as": person, "pid": os.getpid()}))
    try:
        yield token
    finally:
        f.unlink(missing_ok=True)


def confirmed_by_apply(caller: Any) -> bool:
    """Whether this command is a step of an apply the caller confirmed: the token in APPLY_ENV is
    one a running `toprope-apply` took from this same person, and that process is this one's parent."""
    token = os.environ.get(APPLY_ENV)
    if not token or getattr(caller.actor, "kind", None) != "person":
        return False
    try:
        rec = json.loads(_file(token).read_text())
    except (OSError, ValueError):
        return False
    return rec.get("as") == caller.actor.id and rec.get("pid") == os.getppid()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-apply", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("request", help="the request file, .toprope/requests/<id>.yaml")
    ap.add_argument("--identity", default="toprope.identity.yaml",
                    help="the identity file your git email is looked up in")
    ap.add_argument("--ship", action="store_true", help="also deliver, preview, deploy, probe and verify the commit "
                    "the request approves; a commit not recorded low risk stops after its preview")
    return ap


def runner(root: Path) -> ModuleType:
    """The repository's request runner, `tools/human_request.py`."""
    path = root / RUNNER
    if not path.is_file():
        raise SystemExit(fixed(f"no {RUNNER} here: toprope-apply runs this repository's human requests",
                               "run it from the repository root"))
    spec = importlib.util.spec_from_file_location("human_request", path)
    if spec is None or spec.loader is None:
        raise SystemExit(fixed(f"{path} cannot be loaded", "run it from the repository root"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    runner(Path.cwd()).apply(a.request, a.identity, ".", with_ship=a.ship)


__all__ = ["APPLY_ENV", "build_parser", "confirmation", "confirmed_by_apply", "main"]
