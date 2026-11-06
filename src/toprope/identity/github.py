"""The approver of a GitHub environment review as the caller (ADR-0039).

`.github/workflows/human-request.yml` runs a request's steps only after the researcher
approves the run in GitHub; it passes the approver's login in `TOPROPE_GITHUB_APPROVER`. This
adapter looks that login up in `toprope.identity.yaml` (`github:` on a person) and resolves
to that person. Credentials are not used, and agents are never resolved this way: an
approval is a person's.

    people:
      ana@example.com: {name: ana, github: ana-gh, roles: [owner]}

Outside GitHub Actions (`GITHUB_ACTIONS` is not `true`) it resolves no one, so a local shell
cannot pose as an approval by setting the variable.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import Caller, Identity
from .git import load_table

ENV = "TOPROPE_GITHUB_APPROVER"


def github_logins(path: str | Path) -> dict[str, Caller]:
    """GitHub login (lower case) → the person it names, from the identity file."""
    import yaml

    from ..decl.yamlio import load_yaml
    try:
        raw = load_yaml(Path(path).read_text()) or {}
    except yaml.YAMLError as e:
        raise ValueError(str(e)) from None
    table = load_table(path)
    out: dict[str, Caller] = {}
    for email, entry in (raw.get("people") or {}).items():
        login = entry.get("github") if isinstance(entry, dict) else None
        if login is None:
            continue
        if not isinstance(login, str) or not login:
            raise ValueError(f"people.{email}: github must be a login")
        if login.lower() in out:
            raise ValueError(f"people.{email}: github login {login} is listed twice")
        out[login.lower()] = table[str(email)]
    return out


class GitHubApprovalIdentity(Identity):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._logins = github_logins(self.path)

    def login(self) -> str:
        return os.environ.get(ENV, "").strip()

    def resolve(self, credentials: str | None = None) -> Caller | None:
        if os.environ.get("GITHUB_ACTIONS") != "true" or not self.login():
            return None
        return self._logins.get(self.login().lower())

    def explain(self) -> str:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return "the github identity resolves only inside the GitHub Actions approval job (ADR-0039)"
        if not self.login():
            return f"{ENV} is not set: no approver"
        return f"GitHub user {self.login()} approved, but is not a person with `github:` in {self.path}"


__all__ = ["ENV", "GitHubApprovalIdentity", "github_logins"]
