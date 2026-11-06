"""Local identity from git (ADR-0037, resolved 2): who is at this terminal is the repository's
git identity (`user.email`), and what they may do is listed in the repository
(`toprope.identity.yaml`). No tokens to manage on a local machine.

    # toprope.identity.yaml
    people:
      ana@example.com: {name: ana, roles: [owner, approver]}
    agents:                      # optional: an agent's own git email, acting for a person
      bot@example.com:
        name: bot
        roles: [owner]
        on_behalf_of: ana@example.com
        grant: {id: drafting, actions: [propose_element, ask_question]}

An actor's id is `name <email>`, the name taken from the file (not from each machine's git
config), so the same person has the same id everywhere.

A git email is self-asserted: anyone at the terminal can set it. So this adapter is for a
person's own machine only (`toprope-run`); a shared server resolves credentials with `jwt`.
`toprope-run` adds one guard for actions that require a person: it asks on the terminal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..types import Actor, Grant
from . import Caller, Identity, str_list

FILE = "toprope.identity.yaml"


def git_email(root: str | Path = ".") -> str:
    """The repository's `user.email` (local, then global config), or '' when there is none."""
    try:
        out = subprocess.run(["git", "-C", str(root), "config", "user.email"], capture_output=True,
                             text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def _entry(email: str, c: Any, kind: str) -> Actor:
    if not isinstance(c, dict):
        raise ValueError("an entry is a mapping with name and roles")
    name = c.get("name", email.split("@")[0])
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    return Actor(f"{name} <{email}>", kind, str_list(c.get("roles", []), "roles"))


def load_table(path: str | Path) -> dict[str, Caller]:
    """email → Caller, from the identity file. Raises ValueError naming the bad entry."""
    import yaml
    raw = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(raw, dict) or set(raw) - {"people", "agents"}:
        raise ValueError("the file has `people` and optionally `agents`")
    people = raw.get("people") or {}
    agents = raw.get("agents") or {}
    if not isinstance(people, dict) or not isinstance(agents, dict):
        raise ValueError("`people` and `agents` map an email to an entry")
    table: dict[str, Caller] = {}
    for email, c in people.items():
        try:
            table[str(email)] = Caller(_entry(str(email), c, "person"))
        except ValueError as e:
            raise ValueError(f"people.{email}: {e}") from None
    for email, c in agents.items():
        try:
            if str(email) in table:
                raise ValueError("already listed as a person")
            principal = table.get(str(c.get("on_behalf_of"))) if isinstance(c, dict) else None
            if principal is None:
                raise ValueError("on_behalf_of must be the email of a listed person")
            g = c.get("grant")
            if not isinstance(g, dict) or not isinstance(g.get("id"), str):
                raise ValueError("an agent needs a grant with an id and its actions")
            grant = Grant(g["id"], frozenset(str_list(g.get("actions", []), "grant.actions")),
                          None if g.get("targets") is None else frozenset(str_list(g["targets"], "grant.targets")))
            table[str(email)] = Caller(_entry(str(email), c, "agent"), principal.actor, grant)
        except ValueError as e:
            raise ValueError(f"agents.{email}: {e}") from None
    return table


class GitIdentity(Identity):
    """Resolves the repository's git identity through the identity file. Credentials are not used."""

    def __init__(self, path: str | Path, root: str | Path = "."):
        self.path, self.root = Path(path), Path(root)
        self._table = load_table(self.path)

    def email(self) -> str:
        return git_email(self.root)

    def resolve(self, credentials: str | None = None) -> Caller | None:
        email = self.email()
        return self._table.get(email) if email else None

    def explain(self) -> str:
        """Why no caller resolved, in words a person can act on."""
        email = self.email()
        if not email:
            return "no git identity here: set it with `git config user.email YOU@EXAMPLE.COM`"
        return f"your git email {email} is not listed in {self.path} (ask the owner to add you)"


__all__ = ["FILE", "GitIdentity", "git_email", "load_table"]
