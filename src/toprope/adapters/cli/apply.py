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

The one confirmation stands for each person-only step's own terminal prompt, and the guard is
never weaker than that prompt: `toprope-run` skips its prompt only when its standard input is a
terminal (the steps inherit the apply's) and the token `toprope-apply` gives its steps names a
record, in a directory only you can write, of the same person and of `toprope-run`'s parent
process. Without a terminal it refuses, token or not; with a token that does not check out it
refuses too, rather than ask. What this guarantees is what the prompt guaranteed: a process with
no terminal (an agent's ordinary shell, a script) cannot take a person-only step as you. It is not
a security boundary: a process of yours that fakes a terminal can also write such a record.

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
import signal
import stat
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


def _private(path: Path, kind: int) -> bool:
    """`path` is of `kind` (a directory or a file, not a link), owned by this user, and no one else
    may read or write it."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    owner = st.st_uid == os.getuid() if hasattr(os, "getuid") else True
    return stat.S_IFMT(st.st_mode) == kind and owner and not st.st_mode & 0o077


@contextmanager
def confirmation(person: str) -> Iterator[str]:
    """A token for the steps of one confirmed apply: it names the person who confirmed and the
    process that asked them, and it is gone when the apply ends (also on SIGTERM). Kept outside the
    repository, in a directory only this user may use; a directory someone else owns, or opened
    to others, is refused."""
    token = secrets.token_hex(16)
    d = _dir()
    try:
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(fixed(f"cannot make {d}: {e.strerror}", "make it yours with mode 0700, or set TMPDIR "
                               "to a directory of your own")) from None
    if not _private(d, stat.S_IFDIR):
        raise SystemExit(fixed(f"{d} is not a directory only you own and use (mode 0700)",
                               f"remove it, or set TMPDIR to a directory of your own, then apply again"))
    f = _file(token)
    fd = os.open(f, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(json.dumps({"as": person, "pid": os.getpid()}))
    def interrupted(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt         # stopped like Ctrl-C: what ran is recorded, the rest is left

    installed, before = False, None
    try:
        before, installed = signal.signal(signal.SIGTERM, interrupted), True
    except ValueError:                  # not the main thread: SIGTERM keeps its handler
        pass
    try:
        yield token
    finally:
        f.unlink(missing_ok=True)
        if installed:
            signal.signal(signal.SIGTERM, before if before is not None else signal.SIG_DFL)


def confirmed_by_apply(caller: Any) -> bool:
    """Whether the token in APPLY_ENV names a record, in this user's private directory, of a
    confirmation `toprope-apply` took from this same person, and that apply is this process's
    parent. The caller (`toprope-run`) also requires a terminal: see the module's docstring."""
    token = os.environ.get(APPLY_ENV)
    if not token or getattr(caller.actor, "kind", None) != "person":
        return False
    f = _file(token)
    if not (_private(_dir(), stat.S_IFDIR) and _private(f, stat.S_IFREG)):
        return False
    try:
        rec = json.loads(f.read_text())
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
