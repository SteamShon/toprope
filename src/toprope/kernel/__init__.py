"""Kernel services as declared effects (ADR-0028).

The catalog is the kernel itself (ADR-0027). An action calls a service with
`effects: [{call: <service>, with: {<input>: <expression>}, reply: <action>}]`. The call is
appended as an `EffectRequested` outbox event and run after the append. The result comes
back as a command from `external:kernel` to the reply action, keyed by the effect id.

Every result has every field of its service, always: `ok`, `error` ("" when ok), and the
service's own fields (defaults when the call failed). So a reply action may require any of
them, and the declaration decides what a failure means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KERNEL = "external:kernel"


@dataclass(frozen=True)
class Service:
    name: str
    description: str
    inputs: dict[str, str]                  # input → type (all inputs are required)
    # field → type: boolean | integer | number | string | strings (a list of strings)
    result: dict[str, str] = field(default_factory=dict)   # field → type, besides ok and error

    def fields(self) -> dict[str, str]:
        return {"ok": "boolean", "error": "string", **self.result}

    def failure(self, error: str) -> dict[str, Any]:
        default = {"boolean": False, "integer": 0, "number": 0.0, "string": "", "strings": []}
        return {**{k: default[t] for k, t in self.fields().items()}, "ok": False, "error": error}


CATALOG: dict[str, Service] = {s.name: s for s in (
    Service("validate", "Validate a declaration.", {"declaration": "string"},
            {"errors": "integer", "warnings": "integer", "summary": "string"}),
    Service("compile", "Compile a declaration into its domain interface.", {"declaration": "string"},
            {"objects": "integer", "actions": "integer", "elements": "integer", "summary": "string"}),
    Service("check_composition", "Check a composition's members and wiring (ADR-0026).", {"composition": "string"},
            {"issues": "integer", "summary": "string"}),
    Service("run_harness", "Run the generated harness on a declaration.", {"declaration": "string"},
            {"findings": "integer", "cells_covered": "integer", "unreachable": "integer", "summary": "string"}),
    Service("world_map", "Build a declaration's world map.", {"declaration": "string"},
            {"undecided": "integer", "unreachable": "integer", "edges": "integer"}),
    Service("read_source", "Count a workspace source's redacted chunks (local-only respected).", {"source": "string"},
            {"chunks": "integer", "local_only": "boolean"}),
    Service("fetch_source", "Fetch a workspace link source into its snapshot.", {"source": "string"},
            {"sha256": "string"}),
    # Commits (ADR-0029). `commit` returns an `id`, so a reply may create the Commit object.
    Service("commit", "Snapshot a working copy as an immutable commit (no new commit if unchanged).",
            {"declaration": "string"},
            {"id": "string", "seq": "integer", "content": "string", "created": "boolean", "parent": "string",
             "interface": "string", "to_review": "strings", "last_approved": "string"}),
    Service("diff", "The semantic diff between two commits: what changed directly.",
            {"domain": "string", "from": "string", "to": "string"},
            {"changed": "strings", "added": "strings", "removed": "strings", "to_review": "strings"}),
    Service("checkout", "Load a commit's content into a working copy, to revert to it or build on it; "
            "refused when the working copy has uncommitted changes. Committing it makes a new commit.",
            {"domain": "string", "commit": "string", "declaration": "string"},
            {"content": "string"}),
    Service("approve_commit", "Merge a commit into main and tag what main then points to (ADR-0033); "
            "immutable. The calling person must be the approver.",
            {"domain": "string", "commit": "string", "approver": "string"},
            {"approved": "boolean", "main": "string"}),
    Service("preview", "Build a commit for deployment: its harness and world map.",
            {"domain": "string", "commit": "string"},
            {"build": "string", "harness_ok": "boolean"}),
    Service("deploy", "Point an environment at a commit, under the fixed floor (ADR-0022, ADR-0029). "
            "The calling person must be the approver.",
            {"domain": "string", "commit": "string", "approver": "string"},
            {"deployed": "boolean"}),
)}

__all__ = ["CATALOG", "KERNEL", "Service"]
