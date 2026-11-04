"""The authoring MCP (ADR-0014, ADR-0017): the user's own agent drafts and interviews
through these tools, with no Toprope runtime of its own. It runs locally over stdio for the
domain owner; it has no network transport.

Confirmation is human-only. `confirm` shows the owner an MCP elicitation listing the
elements (a resolver, so it works on every protocol version), and confirms only if the
owner accepts there. A client without elicitation support is refused by the protocol
(missing capability), and the owner confirms with `toprope-author confirm` instead.
"""

from __future__ import annotations

import functools
from typing import Annotated, Any

from mcp.server.elicitation import AcceptedElicitation, ElicitationResult
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from . import AuthoringError, Workspace


class Confirmation(BaseModel):
    confirm: bool = Field(description="Confirm these elements as right")


def ask_owner(paths: list[str]) -> Elicit[Confirmation]:
    """The resolver for `confirm`: the owner sees the elements in their client's prompt."""
    listing = "\n".join(f"- {p}" for p in paths)
    return Elicit(f"Confirm these drafted elements as right?\n{listing}", Confirmation)


def _guard(fn):
    @functools.wraps(fn)
    def wrap(*a, **kw):
        try:
            return fn(*a, **kw)
        except AuthoringError as e:
            raise ToolError(str(e)) from None
    return wrap


def build_authoring_server(ws: Workspace, **server_kwargs: Any) -> MCPServer:
    server = MCPServer(name="toprope-authoring", instructions=(
        "Draft a Toprope declaration from sources and interview its owner, stage by stage "
        "(ADR-0025, ADR-0014). For the current stage: draft what the sources support (propose, "
        "citing a source ref), then ask the owner the stage's whole bundle from questions() at "
        "once, show them progress, and record their own words with answer(bundle_id, ...). Move "
        "on when questions() moves to the next stage. Whenever a term comes up that a newcomer could "
        "misread, propose glossary.<term> in the owner's words. You write only `proposed`; the owner confirms."), **server_kwargs)

    @_guard
    def list_sources() -> list[dict[str, Any]]:
        """Configured sources: id, kind, path, local_only, number of chunks. Local-only sources
        are listed but their content is never served."""
        return ws.list_sources()

    @_guard
    def read_source(source_id: str, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        """Redacted chunks of a source, each with the `ref` to cite. Recorded in the usage log."""
        return ws.read_source(source_id, offset, limit)

    @_guard
    def search_sources(query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Case-insensitive search across non-local sources: refs and redacted snippets."""
        return ws.search_sources(query, limit)

    @_guard
    def get_draft() -> dict[str, Any]:
        """The current draft declaration (YAML as JSON)."""
        return ws.draft()

    @_guard
    def propose(path: str, value: Any, source_ref: str, quote: str | None = None) -> dict[str, Any]:
        """Set one element of the draft as `proposed`, citing a source chunk. Paths: objects.X,
        links.X, actions.X, actions.X.preconditions.ID, invariants.ID,
        transitions.Obj.matrix.State.action (a state name, {deny: ...}, n/a or undecided),
        and plain keys such as roles, glossary.Term, purpose, world. A null value removes it.
        The draft is written only if it still parses; validation issues are returned."""
        return ws.propose(path, value, source_ref, quote)

    @_guard
    def questions(limit: int = 10, stage: str | None = None) -> dict[str, Any]:
        """The current stage's bundle of questions (ADR-0025), with the progress of every stage.
        Stages: sources, purpose, cast (roles, objects, links), actions, transitions,
        invariants, world (fixtures, scenarios), handoffs, review. Ask the whole bundle at once,
        show the owner the progress, and record their answer with answer(bundle_id, ...)."""
        return ws.questions(limit, stage=stage)

    @_guard
    def progress() -> dict[str, Any]:
        """Where the domain stands: each stage done, current, todo or skipped, with counts."""
        return ws.progress()

    @_guard
    def skip_stage(stage: str, reason: str) -> dict[str, Any]:
        """Record, in the owner's words, that an optional stage (invariants, handoffs) has
        nothing in this domain."""
        return ws.skip_stage(stage, reason)

    @_guard
    def fetch_source(source_id: str) -> list[dict[str, Any]]:
        """Fetch a link source once into its snapshot, so it can be read and cited."""
        return ws.fetch(source_id)

    @_guard
    def answer(question_id: str, answer: str, decisions: list[dict[str, Any]],
               question: str | None = None) -> dict[str, Any]:
        """Record the owner's answer in their own words, and apply its decisions
        ([{path, value}]) as proposed elements that cite the answer."""
        return ws.answer(question_id, answer, decisions, question)

    def confirm(paths: list[str],
                owner: Annotated[ElicitationResult[Confirmation], Resolve(ask_owner)]) -> dict[str, Any]:
        """Ask the owner, through the client's elicitation prompt, to confirm these elements.
        Only the owner's acceptance confirms them. A client that cannot show an elicitation
        is refused: the owner then runs `toprope-author confirm PATH...`."""
        if not isinstance(owner, AcceptedElicitation) or not owner.data.confirm:
            return {"confirmed": [], "reason": "The owner did not confirm."}
        try:
            return ws.confirm(paths, via="elicitation")
        except AuthoringError as e:
            raise ToolError(str(e)) from None

    @_guard
    def check_draft() -> dict[str, Any]:
        """Validate the draft, run the model-level harness on it, and count undecided and
        unconfirmed cells: one compiled iteration."""
        return ws.check()

    for fn in (list_sources, read_source, search_sources, fetch_source, get_draft, propose, questions,
               progress, skip_stage, answer, confirm, check_draft):
        server.add_tool(fn, name=fn.__name__)
    return server
