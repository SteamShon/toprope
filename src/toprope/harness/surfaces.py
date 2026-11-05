"""Levels the harness runs at (ADR-0010 §4): the model interpreter, Execution and an MCP client
against the generated server. Each gives the same synchronous interface, so one test runs
unchanged on every level, and parity is a plain comparison of what they return."""

from __future__ import annotations

import asyncio
import json
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..decl.models import Domain
from ..exec import Execution
from ..identity import Caller, StaticIdentity
from ..kernel import KERNEL
from ..semantics.model import ReferenceModel
from ..semantics.types import Actor, Command, Event, Outcome
from ..store import EventStore, MemoryEventStore

Observed = dict[str, Any]   # {"status", "code"?, "reason"?, "state"?}: what a caller sees


def observed(o: Outcome) -> Observed:
    """The caller-visible outcome, normalized through JSON (the shape MCP returns)."""
    from ..adapters.mcp import outcome_json
    return json.loads(json.dumps(outcome_json(o)))


READER = Actor("harness-reader", "person", ())   # reads state through MCP; holds no role


def token(actor: Actor) -> str:
    return f"harness:{actor.id}"


class Surface(ABC):
    name: str

    @abstractmethod
    def seed(self, obj: str, data: dict[str, Any]) -> None:
        """Setup only: load an object as a fixture, not through an action."""

    @abstractmethod
    def do(self, actor: Actor, action: str, target: str, params: dict[str, Any], key: str) -> Observed: ...

    @abstractmethod
    def state(self, oid: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def allowed(self, actor: Actor, oid: str) -> list[str]: ...

    @abstractmethod
    def lookup(self, oid: str) -> tuple[str, dict[str, Any]] | None:
        """For the harness's own invariant checks: (type, state) of any object."""

    def events(self, oid: str) -> list[Event] | None:
        """The stored event stream, where the level has one."""
        return None

    def close(self) -> None:
        pass


class ModelSurface(Surface):
    name = "model"

    def __init__(self, d: Domain, clock: Callable[[], datetime], store: EventStore | None = None):
        self.m = ReferenceModel(d, store or MemoryEventStore(), clock=clock, seed_world=False)

    def seed(self, obj, data):
        self.m.seed(obj, data, only_if_new=True)

    def do(self, actor, action, target, params, key):
        return observed(self.m.execute(Command(actor, action, target, dict(params), key)))

    def state(self, oid):
        return self.m.state(oid)

    def allowed(self, actor, oid):
        return self.m.allowed_actions(oid, actor)

    def lookup(self, oid):
        return self.m.lookup(oid)

    def events(self, oid):
        return self.m.store.read(oid)


class _Identities(StaticIdentity):
    """Every world actor gets a token. Tokens are added as actors appear."""

    def __init__(self):
        super().__init__({})

    def add(self, actor: Actor) -> str:
        self._callers.setdefault(token(actor), Caller(actor))
        return token(actor)


class ExecutionSurface(Surface):
    name = "execution"

    def __init__(self, d: Domain, clock: Callable[[], datetime], store: EventStore | None = None):
        self.ids = _Identities()
        self.ex = Execution(d, store or MemoryEventStore(), self.ids, clock=clock)

    def seed(self, obj, data):
        self.ex.seed(obj, data)

    def do(self, actor, action, target, params, key):
        if actor.id == KERNEL:   # a kernel reply never comes through credentials (ADR-0028)
            return observed(self.ex.receive_kernel_reply(key, action, target, dict(params)))
        return observed(self.ex.submit(self.ids.add(actor), action, target, dict(params), key))

    def state(self, oid):
        return self.ex.state(oid)

    def allowed(self, actor, oid):
        return self.ex.allowed_actions(oid, actor if actor.kind == "system" else Caller(actor))

    def lookup(self, oid):
        return self.ex.lookup(oid)

    def events(self, oid):
        return self.ex.history(oid)


class MCPSurface(ExecutionSurface):
    """An in-process MCP client session against `build_server`, on its own event loop thread.
    Setup (seeding) goes to the Execution behind the server; every action and read under test
    goes through MCP tools."""
    name = "mcp"

    def __init__(self, d: Domain, clock: Callable[[], datetime], store: EventStore | None = None,
                 build: Callable[..., Any] | None = None):
        super().__init__(d, clock, store)
        from mcp import Client

        from ..adapters.mcp import build_server
        self._token: str | None = None
        server = (build or build_server)(self.ex, lambda: self._token)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        ready = threading.Event()

        async def session():
            # One task owns the session from enter to exit (anyio cancel scopes require it).
            self._stop = asyncio.Event()
            async with Client(server) as c:
                self._client = c
                ready.set()
                await self._stop.wait()

        self._session = asyncio.run_coroutine_threadsafe(session(), self._loop)
        if not ready.wait(30):
            self._session.result(timeout=1)   # surface the startup error
            raise RuntimeError("the MCP session did not start")

    def _call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=60)

    def _tool(self, actor: Actor | None, name: str, args: dict[str, Any]) -> Any:
        self._token = self.ids.add(actor) if actor else None
        res = self._call(self._client.call_tool(name, args))
        if res.is_error:
            return {"status": "error", "reason": res.content[0].text if res.content else ""}
        sc = res.structured_content
        if isinstance(sc, dict) and set(sc) == {"result"}:
            return sc["result"]
        return sc if sc is not None else json.loads(res.content[0].text)

    def do(self, actor, action, target, params, key):
        if actor.id == KERNEL:   # the kernel is not an MCP caller: its replies go to Execution
            return super().do(actor, action, target, params, key)
        spec = self.ex.d.actions[action]
        arg = "new_id" if spec.creates else "target_id"
        return self._tool(actor, action, {arg: target, "idempotency_key": key, **params})

    def allowed(self, actor, oid):
        if actor.id == KERNEL:
            return super().allowed(actor, oid)
        return self._tool(actor, "allowed_actions", {"object_id": oid})

    def state(self, oid):
        st = self._tool(READER, "get_object", {"object_id": oid})
        return None if set(st) == {"error"} else st

    def close(self):
        try:
            self._loop.call_soon_threadsafe(self._stop.set)
            self._session.result(timeout=30)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(5)


LEVELS: dict[str, type[Surface]] = {"model": ModelSurface, "execution": ExecutionSurface, "mcp": MCPSurface}
