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
    result: dict[str, str] = field(default_factory=dict)   # field → type, besides ok and error

    def fields(self) -> dict[str, str]:
        return {"ok": "boolean", "error": "string", **self.result}

    def failure(self, error: str) -> dict[str, Any]:
        default = {"boolean": False, "integer": 0, "number": 0.0, "string": ""}
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
    Service("preview", "Build a preview: the harness and world map for a declaration.", {"declaration": "string"},
            {"build": "string", "harness_ok": "boolean"}),
    Service("deploy", "Deploy a previewed build under the fixed floor (ADR-0022).", {"build": "string", "approver": "string"},
            {"deployed": "boolean"}),
)}

__all__ = ["CATALOG", "KERNEL", "Service"]
