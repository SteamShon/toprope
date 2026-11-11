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
    inputs: dict[str, str]                  # input → type (required unless listed in `optional`)
    # field → type: boolean | integer | number | string | strings (a list of strings)
    result: dict[str, str] = field(default_factory=dict)   # field → type, besides ok and error
    optional: frozenset[str] = frozenset()  # inputs a call may leave out, or pass as null

    def required(self) -> list[str]:
        return [i for i in self.inputs if i not in self.optional]

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
    # The interview (ADR-0025, ADR-0037): generic operations on a workspace's working copy.
    Service("search_sources", "Search the workspace's sources (redacted; local-only never served).",
            {"query": "string"}, {"refs": "strings"}),
    Service("stage_questions", "The current stage of the working copy and its bundle of questions.", {},
            {"stage": "string", "bundle": "string", "questions": "strings", "text": "string"}),
    Service("propose_element", "Write a drafted element into the working copy, citing a source chunk; "
            "always `proposed`. `value` is JSON.", {"path": "string", "value": "string", "source": "string"},
            {"issues": "integer", "summary": "string"}),
    Service("record_answer", "Record the owner's answer in their words; its decisions (JSON list of "
            "{path, value}) become proposed elements citing it.",
            {"question": "string", "answer": "string", "decisions": "string"}, {"ref": "string"}),
    Service("confirm_element", "Confirm drafted elements (space-separated paths, or `all` for every "
            "proposed one). The calling person must be the approver.",
            {"paths": "string", "approver": "string"}, {"confirmed": "strings"}),
    Service("skip_stage", "Record that an optional stage has nothing, with the owner's reason.",
            {"stage": "string", "reason": "string"}, {"skipped": "boolean"}),
    # Commits (ADR-0029). `commit` returns an `id`, so a reply may create the Commit object.
    Service("commit", "Snapshot a working copy as an immutable commit (no new commit if unchanged). "
            "Cite its evidence with `cite_evidence` (ADR-0041).",
            {"declaration": "string"},
            {"id": "string", "seq": "integer", "content": "string", "created": "boolean", "parent": "string",
             "interface": "string", "to_review": "strings", "last_approved": "string", "domain": "string",
             "branch": "string", "author": "string"}),
    Service("cite_evidence", "Cite evidence for a commit (ADR-0041): `kind` is interview or source (a chunk "
            "ref), check (a check recorded on the commit), event (`<stream>@<version>` in the domain's "
            "environment) or approval-run (a GitHub Actions run that approved a human request). The ref "
            "must resolve; a claim with no pointer is refused.",
            {"domain": "string", "commit": "string", "kind": "string", "ref": "string"},
            {"strength": "string"}),
    Service("diff", "The semantic diff between two commits: what changed directly.",
            {"domain": "string", "from": "string", "to": "string"},
            {"changed": "strings", "added": "strings", "removed": "strings", "to_review": "strings"}),
    Service("checkout", "Load a commit's content into a working copy, to revert to it or build on it; "
            "refused when the working copy has uncommitted changes. Committing it makes a new commit.",
            {"domain": "string", "commit": "string", "declaration": "string"},
            {"content": "string"}),
    Service("merge_main", "Bring main into a branch's working copy (a semantic 3-way merge) and list the "
            "conflicts for the person to resolve; the next commit on the branch records both parents.",
            {"domain": "string", "branch": "string", "declaration": "string"},
            {"merge": "string", "up_to_date": "boolean", "conflicts": "integer", "paths": "strings"}),
    Service("change_check", "Run the change check on a commit against its merge base with main, and "
            "record it on the commit (ADR-0009, ADR-0032).",
            {"domain": "string", "commit": "string"},
            {"passed": "boolean", "errors": "integer", "warnings": "integer", "failing": "strings",
             "summary": "string"}),
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
    Service("probe", "Check a deployed commit in use: the environment runs this commit's build and the "
            "floor still holds, its scenarios pass at the execution level, and every object in the "
            "deployed store meets every invariant. Recorded on the commit as the `probes` check.",
            {"domain": "string", "commit": "string"},
            {"passed": "boolean", "summary": "string"}),
)}

__all__ = ["CATALOG", "KERNEL", "Service"]
