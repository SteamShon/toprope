"""`toprope-proxy`: a declaration's rules in front of an existing MCP server (ADR-0052).

An agent connects to the proxy instead of the server it used. The proxy offers the upstream tools
its binding names, with their own names and input schemas, and nothing else:

- a **gated** tool is a declared action. The kernel decides first (actor, preconditions, the
  transition cell, outcome rules); a refusal never reaches the server. An allowed call is the
  action's `call: mcp:<tool>` effect (ADR-0028), sent once by its effect id; the server's answer
  comes back through the reply action, and is what the agent receives;
- a **read** tool (`read: true`) passes through, recorded in the audit log, not gated;
- a tool with no binding is not offered.

The binding (YAML):

    upstream: {command: [python, server.py]}        # or {url: https://…/mcp}
    tools:
      refund_order:
        action: refund                               # the declared action this tool is
        target: order_id                             # the argument naming the object (or `new_id:`)
        params: {amount: amount}                     # action param: tool argument (default: same names)
        result: {refund_id: string}                  # fields of the answer the reply may take
        load: get_order                              # an order the gate has not seen: read it here
      get_order: {read: true}
    confirmed: {by: dana, at: "2026-11-10T09:00:00+00:00", sha256: 3f…}   # written by --confirm-binding

A binding is served only with a person's confirmation record whose `sha256` is the hash of its
`upstream` and `tools` as they are now (`Binding.digest`): one no person confirmed, or one changed
since, is refused until a person confirms it again (`toprope-proxy --confirm-binding`, ADR-0052 §7).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..errors import fixed
from ..kernel import UPSTREAM, Service, register_upstream
from ..kernel.services import KernelServices

JSON_TYPES = {"string": "string", "integer": "integer", "number": "number", "boolean": "boolean"}


@dataclass
class ToolBinding:
    name: str
    read: bool = False
    action: str | None = None
    target: str | None = None          # the argument that names the object the action targets
    new_id: str | None = None          # for a creating action: the argument that names the new object
    params: dict[str, str] = field(default_factory=dict)   # action param -> tool argument
    result: dict[str, str] = field(default_factory=dict)   # answer field -> service type
    hidden: set[str] = field(default_factory=set)          # optional arguments the gate never sees: not offered
    load: str | None = None            # a read tool that returns an object the gate has not seen yet


def digest(upstream: Any, tools: Any) -> str:
    """The hash a confirmation records: the binding's `upstream` and `tools` as data, so comments
    and layout do not count, and any change to what is bound does."""
    return hashlib.sha256(json.dumps({"upstream": upstream, "tools": tools}, sort_keys=True,
                                     default=str).encode()).hexdigest()


@dataclass
class Binding:
    upstream: dict[str, Any]
    tools: dict[str, ToolBinding]
    digest: str = ""                   # of `upstream` and `tools` as loaded
    confirmed: dict[str, Any] | None = None   # {by, at, sha256}: who confirmed which content

    def unconfirmed(self) -> str | None:
        """Why the binding may not be served, or None when a person confirmed it as it is."""
        c = self.confirmed
        if not c:
            return "no person has confirmed the binding"
        if c.get("sha256") != self.digest:
            return f"the binding changed after {c.get('by')} confirmed it at {c.get('at')}"
        return None

    @classmethod
    def load(cls, path: str | Path) -> Binding:
        from ..decl import load_yaml
        try:
            data = load_yaml(Path(path).read_text()) or {}
        except OSError as e:
            raise SystemExit(fixed(f"cannot read the binding {path}: {e.strerror}", "give the binding's YAML file")) from None
        if not isinstance(data, dict) or not isinstance(data.get("upstream"), dict) or not isinstance(data.get("tools"), dict):
            raise SystemExit(fixed(f"the binding {path} needs `upstream:` and `tools:` mappings",
                                   "see `toprope-proxy --help` for the binding's shape"))
        up = data["upstream"]
        if ("command" in up) == ("url" in up):
            raise SystemExit(fixed(f"the binding {path}: `upstream` has exactly one of `command` or `url`",
                                   "give `command: [program, args…]` for stdio, or `url:` for streamable HTTP"))
        extra = sorted(set(map(str, data)) - {"upstream", "tools", "confirmed"})
        if extra:
            raise SystemExit(fixed(f"the binding {path} has unknown key(s) {', '.join(extra)}",
                                   "keep only `upstream`, `tools` and the `confirmed` record `toprope-proxy "
                                   "--confirm-binding` writes"))
        conf = data.get("confirmed")
        if conf is not None and not (isinstance(conf, dict) and {"by", "at", "sha256"} <= set(conf)):
            raise SystemExit(fixed(f"the binding {path}: `confirmed` is not a confirmation record",
                                   "remove it, and let a person confirm with `toprope-proxy --confirm-binding`"))
        tools = {}
        known = {"read", "action", "target", "new_id", "params", "result", "load"}   # `hidden` is computed
        for name, spec in data["tools"].items():
            spec = spec or {}
            bad = sorted(set(spec) - known) if isinstance(spec, dict) else ["(not a mapping)"]
            if bad:
                raise SystemExit(fixed(f"the binding {path}: tool {name} has unknown key(s) {', '.join(bad)}",
                                       f"use only the keys {', '.join(sorted(known))}"))
            tb = ToolBinding(str(name), **spec)
            if tb.read == bool(tb.action):
                raise SystemExit(fixed(f"the binding {path}: tool {name} is either `read: true` or an `action`",
                                       "bind it to a declared action, or mark it read-only"))
            if tb.action and bool(tb.target) == bool(tb.new_id):
                raise SystemExit(fixed(f"the binding {path}: tool {name} names exactly one of `target` or `new_id`",
                                       "name the argument that identifies the object"))
            tools[str(name)] = tb
        return cls(up, tools, digest(up, data["tools"]), conf)


class Upstream:
    """One MCP client session to the upstream server, on its own event loop thread, so the
    synchronous kernel can call it."""

    def __init__(self, target: Any):
        from mcp import Client
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        ready = threading.Event()

        async def session() -> None:
            self._stop = asyncio.Event()
            async with Client(target) as c:
                self.client = c
                ready.set()
                await self._stop.wait()

        self._session = asyncio.run_coroutine_threadsafe(session(), self._loop)
        for _ in range(600):                                     # up to a minute, unless the session fails first
            if ready.wait(0.1) or self._session.done():
                break
        if not ready.is_set():
            why = "it did not answer within a minute"
            if self._session.done() and self._session.exception() is not None:
                e = self._session.exception()
                why = f"{type(e).__name__}: {e}"
            self._loop.call_soon_threadsafe(self._loop.stop)
            raise SystemExit(fixed(f"the upstream MCP server did not start: {why}",
                                   "check the binding's `upstream` command or URL, and that the server runs on its own"))

    @classmethod
    def open(cls, spec: dict[str, Any]) -> Upstream:
        if "url" in spec:
            return cls(str(spec["url"]))
        from mcp import StdioServerParameters
        cmd = [str(x) for x in spec["command"]]
        return cls(StdioServerParameters(command=cmd[0], args=cmd[1:], env=spec.get("env")))

    def _run(self, coro: Any, timeout: float = 120) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    def tools(self) -> dict[str, Any]:
        return {t.name: t for t in self._run(self.client.list_tools()).tools}

    def call(self, tool: str, args: dict[str, Any]) -> Any:
        return self._run(self.client.call_tool(tool, args))

    def close(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._stop.set)
            self._session.result(timeout=30)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(5)


def answer(res: Any) -> dict[str, Any]:
    """An upstream result as data: its structured content, or its text read as JSON, or the text."""
    sc = getattr(res, "structured_content", None)
    if isinstance(sc, dict):
        return sc
    text = "".join(getattr(c, "text", "") for c in getattr(res, "content", None) or [])
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"result": data}
    except ValueError:
        return {"result": text}


class UpstreamServices(KernelServices):
    """Runs a declaration's `call: mcp:<tool>` effects against the upstream server. The full
    answer to each call is kept, by tool and inputs, for the proxy to hand back to the agent (the
    reply action takes only the fields the binding names)."""

    def __init__(self, upstream: Upstream, fallback: KernelServices | None = None):
        self.upstream, self.fallback = upstream, fallback
        self.last: dict[str, Any] = {}

    def run(self, service: str, inputs: dict[str, Any]) -> dict[str, Any]:
        if not service.startswith(UPSTREAM):
            if self.fallback is None:
                raise RuntimeError(fixed(f"no kernel services in this proxy for {service}",
                                         "call only `mcp:` tools from a declaration served by toprope-proxy"))
            return self.fallback.run(service, inputs)
        tool = service[len(UPSTREAM):]
        try:
            res = self.upstream.call(tool, inputs)
        except Exception as e:                                    # no answer: it may or may not have acted
            self.last[key(tool, inputs)] = e
            raise
        self.last[key(tool, inputs)] = res
        data = answer(res)
        if getattr(res, "is_error", False):
            return {"ok": False, "error": str(data.get("result") or data)}
        return {"ok": True, **data}


class StoreLock:
    """One gated call at a time across every proxy on the same store: a file lock beside a SQLite
    file or a JSONL folder, held around the gate's decision, the call and its reply."""

    def __init__(self, store: str):
        kind, _, where = store.partition(":")
        refuse = fixed(f"toprope-proxy cannot share its gate over the store {store!r}",
                       "use `--store sqlite:FILE` (or `jsonl:DIR`) with a real path; a memory store forgets what "
                       "was done, and several proxies on one database need a shared lock M0b brings")
        if kind not in ("sqlite", "jsonl") or not where.strip() or where.startswith((":memory:", "file:")):
            raise SystemExit(refuse)
        try:
            import fcntl  # noqa: F401  (POSIX file locks; checked at start, not at the first call)
        except ImportError:
            raise SystemExit(fixed("toprope-proxy needs POSIX file locks, which this system lacks",
                                   "run the proxy on Linux or macOS")) from None
        real = Path(where).resolve()                    # a symlinked store shares its target's lock
        path = real.with_name(real.name + ".proxy.lock") if kind == "sqlite" else real / ".proxy.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self._local = path, threading.Lock()

    def __enter__(self) -> StoreLock:
        import fcntl
        self._local.acquire()
        self._f = open(self.path, "a")
        fcntl.flock(self._f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc: object) -> None:
        import fcntl
        try:
            fcntl.flock(self._f, fcntl.LOCK_UN)
            self._f.close()
        finally:
            self._local.release()


def key(tool: str, inputs: dict[str, Any]) -> str:
    return json.dumps([tool, inputs], sort_keys=True, default=str)


def _scalar(spec: Any) -> str | None:
    """A JSON schema a declaration can pass: a scalar type, or `anyOf` one scalar and null."""
    if not isinstance(spec, dict):
        return None
    if "type" in spec:
        return JSON_TYPES.get(str(spec["type"]))
    kinds = [s.get("type") for s in spec.get("anyOf") or [] if isinstance(s, dict)]
    rest = [k for k in kinds if k != "null"]
    return JSON_TYPES.get(str(rest[0])) if len(rest) == 1 and len(kinds) == len(spec.get("anyOf") or []) else None


def register(binding: Binding, tools: dict[str, Any], d: Any) -> list[str]:
    """Register each gated tool as a service, typed from the server's input schema, and decide
    what the agent is offered. Every argument the agent can send must be one the gate sees (the
    target, or an action param) and the call passes on (the effect's `with`); an optional one
    that is neither is not offered. Returns the problems, each with its fix."""
    problems = []
    for name, tb in binding.tools.items():
        if name not in tools:
            problems.append(fixed(f"the binding names {name}, which the upstream server does not offer",
                                  f"use one of {', '.join(sorted(tools))}"))
            continue
        hint = getattr(getattr(tools[name], "annotations", None), "read_only_hint", None)
        if tb.read:
            if hint is not True:
                problems.append(fixed(f"the binding marks {name} read-only, but the server does not (readOnlyHint)",
                                      f"bind {name} to a declared action, or leave it out"))
            continue
        if tb.load and tb.load in tools and tb.target not in ((tools[tb.load].input_schema or {}).get("properties") or {}):
            problems.append(fixed(f"tool {name} loads with {tb.load}, which takes no `{tb.target}` argument",
                                  f"name a read tool that takes `{tb.target}`, or drop `load:`"))
        a = d.actions.get(tb.action)
        call = next((e for e in (a.effects if a else []) if e.call == f"{UPSTREAM}{name}"), None)
        if a is None or call is None:
            continue                                              # `check` names it
        schema = tools[name].input_schema or {}
        props, required = schema.get("properties") or {}, set(schema.get("required") or [])
        seen = {tb.new_id or tb.target} | {tb.params.get(p, p) for p in a.params}
        inputs: dict[str, str] = {}
        for arg, spec in props.items():
            if arg not in seen or arg not in call.with_:
                if arg in required:
                    problems.append(fixed(f"{name}.{arg} is required by the server, but the gate never checks it "
                                          f"or the call does not pass it on",
                                          f"map it to a param of {tb.action} (`params:`) and pass it in the effect's "
                                          f"`with`"))
                else:
                    tb.hidden.add(arg)
                continue
            t = _scalar(spec)
            if t is None:
                problems.append(fixed(f"{name}.{arg} is not a string, number or boolean",
                                      "bind a tool whose checked inputs are those, or leave the argument out"))
                continue
            inputs[arg] = t
        register_upstream(Service(f"{UPSTREAM}{name}", str(tools[name].description or name), inputs,
                                  dict(tb.result), frozenset(set(inputs) - required)))
    return problems


def check(d: Any, binding: Binding, *, confirmation: bool = True) -> list[str]:
    """What must hold between the declaration and the binding before anything is served.
    `confirmation=False` leaves out the binding's own confirmation, for `--confirm-binding`."""
    from ..decl import validate_domain
    from ..decl.provenance import proposed_elements
    from ..kernel import UPSTREAM_SERVICES
    problems = [fixed(f"{i.code} at {i.where}: {i.message}", "correct the declaration")
                for i in validate_domain(d) if i.severity == "error"]
    if confirmation and (why := binding.unconfirmed()):   # only what a person confirmed, as it is now, is enforced (ADR-0052 §7)
        problems.append(fixed(why, "a person reads it and confirms it: `toprope-proxy --confirm-binding` with the "
                                   "same --domain, --binding and --identity"))
    unconfirmed = proposed_elements(d.model_dump(mode="json", by_alias=True, exclude_none=True))
    if unconfirmed:                    # agents propose; only what a person confirmed is enforced (ADR-0041)
        problems.append(fixed(f"the declaration has {len(unconfirmed)} element(s) no person has confirmed "
                              f"({', '.join(unconfirmed[:5])}{', …' if len(unconfirmed) > 5 else ''})",
                              "a person confirms them (set `status: confirmed`, or confirm through the authoring "
                              "loop) before the proxy enforces them"))
    for an, a in d.actions.items():
        for e in a.effects:
            if e.call and e.call.startswith(UPSTREAM) and e.call not in UPSTREAM_SERVICES:
                problems.append(fixed(f"action {an} calls {e.call}, which the binding does not bind",
                                      f"bind {e.call[len(UPSTREAM):]} to {an} in the binding, or remove the call"))
    for name, tb in binding.tools.items():
        if tb.read:
            continue
        a = d.actions.get(tb.action)
        if a is None:
            problems.append(fixed(f"tool {name} is bound to {tb.action}, which the declaration does not have",
                                  f"use one of {', '.join(sorted(d.actions))}"))
            continue
        if not any(e.call == f"{UPSTREAM}{name}" for e in a.effects):
            problems.append(fixed(f"action {tb.action} does not call {UPSTREAM}{name}",
                                  f"add the effect `call: {UPSTREAM}{name}` with its inputs and a `reply` action"))
        if tb.load and tb.new_id:
            problems.append(fixed(f"tool {name} creates an object, so there is nothing to load",
                                  "drop `load:` from a creating tool"))
        if tb.load and not (tb.load in binding.tools and binding.tools[tb.load].read):
            problems.append(fixed(f"tool {name} loads objects with {tb.load}, which the binding does not mark "
                                  "`read: true`", f"bind {tb.load} as a read-only tool, or drop `load:`"))
        if bool(a.creates) != bool(tb.new_id):
            problems.append(fixed(f"tool {name}: action {tb.action} {'creates' if a.creates else 'targets'} an object",
                                  f"name its argument with `{'new_id' if a.creates else 'target'}:`"))
    return problems


def build_proxy(ex: Any, binding: Binding, upstream: Upstream, credentials: Any, *,
                audit: str | Path | None = None, lock: Any = None, **server_kwargs: Any) -> Any:
    """The MCP server an agent connects to. `ex` runs with `UpstreamServices` over `upstream`.
    `lock` serialises gated calls; give every proxy on one store the same one (`StoreLock`), or
    two of them can both see an object before either call has moved it."""
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.server.mcpserver.tools import Tool
    from pydantic import Field, create_model

    from ..adapters.mcp import _RawArgs, _StrictArgs
    from ..handoff import EFFECT_PREFIX, effect_id

    offered = upstream.tools()
    services: UpstreamServices = ex.services
    gate = lock or threading.Lock()  # one gated call at a time: the next sees what the last one did

    def log(entry: dict[str, Any]) -> None:
        if audit:
            with open(audit, "a") as f:
                f.write(json.dumps({"at": datetime.now(UTC).isoformat(), **entry}) + "\n")

    def fits(spec: Any, v: Any) -> bool:
        if spec.enum:
            return v in spec.enum
        ok = {"string": isinstance(v, str), "datetime": isinstance(v, str), "boolean": isinstance(v, bool),
              "integer": isinstance(v, int) and not isinstance(v, bool),
              "number": isinstance(v, (int, float)) and not isinstance(v, bool)}.get(spec.type, False)
        return ok and (spec.min is None or v >= spec.min) and (spec.max is None or v <= spec.max)

    def load(name: str, tb: ToolBinding, target: str, who: str) -> None:
        """Read the object from the server before every gated call, so the gate decides on what
        the server says now: a new object is recorded as the server's (a system fixture); for one
        it has, the facts that changed are recorded as read from the server. The stage stays the
        gate's own (ADR-0052 §4): a different stage on the server is drift, for the person."""
        from ..semantics.model import SYSTEM
        from ..semantics.types import Event
        a = ex.d.actions[tb.action]
        obj = ex.d.objects[a.object_type]
        field = ex.d.transitions[a.object_type].field if a.object_type in ex.d.transitions else None
        try:
            res = upstream.call(tb.load, {tb.target: target})
        except Exception as e:                                    # noqa: BLE001 - no answer: refuse, fail closed
            raise ToolError(fixed(f"{name}: could not read {target} with {tb.load} ({type(e).__name__}: {e})",
                                  "ask again when the server answers; nothing was sent")) from None
        if getattr(res, "is_error", False):
            raise ToolError(fixed(f"{name}: {tb.load} could not read {target}: {answer(res).get('result')}",
                                  f"check that {target} exists on the server; nothing was sent"))
        data = {k: v for k, v in answer(res).items() if k in obj.properties}
        found = ex.lookup(target)
        have = found[1] if found else {}
        new = {k: v for k, v in data.items() if not (k == field and found)}   # the stage is the gate's
        merged = {**have, **new}
        missing = [k for k, s in obj.properties.items() if not s.optional and merged.get(k) is None]
        bad = [k for k, v in new.items() if v is not None and not fits(obj.properties[k], v)]
        if missing or bad:
            raise ToolError(fixed(f"{target} from {tb.load} cannot be checked: " + "; ".join(
                [*(f"no {k}" for k in missing), *(f"{k}={new[k]!r} is not a valid {obj.properties[k].type or 'value'}"
                                                  + (f" (one of {obj.properties[k].enum})" if obj.properties[k].enum else "")
                                                  for k in bad)]),
                f"make {tb.load} return {', '.join(sorted(k for k, s in obj.properties.items() if not s.optional))} "
                "with their declared types; nothing was sent"))
        if not found:
            ex.seed(a.object_type, {"id": target, **new})
            log({"tool": tb.load, "caller": who, "loaded": target, "for": name})
        else:
            changed = {k: v for k, v in new.items() if have.get(k) != v}
            if changed:
                ex.store.append(target, ex.store.version(target), [Event(
                    f"{a.object_type}ReadFromServer", target, a.object_type, at=datetime.now(UTC), actor=SYSTEM.ref(),
                    payload={"changes": changed, "params": {}, "action": None, "source": tb.load},
                    domain_version=ex.d.version)])
                log({"tool": tb.load, "caller": who, "refreshed": target, "changed": sorted(changed), "for": name})
            if field and field in data and data[field] != have.get(field):
                log({"tool": tb.load, "caller": who, "drift": target, field: {"gate": have.get(field),
                                                                             "server": data[field]}})

    def make(name: str, tb: ToolBinding) -> Tool:
        up = offered[name]
        schema = json.loads(json.dumps(up.input_schema or {"type": "object", "properties": {}}))
        for arg in tb.hidden:
            schema.get("properties", {}).pop(arg, None)
        if not tb.read:
            schema.setdefault("properties", {})["idempotency_key"] = {
                "type": "string", "description": "Optional. The same key never runs the call twice; "
                                                 "without one, the same caller, tool and arguments count as one call."}

        def fn(**args: Any) -> dict[str, Any]:
            token = credentials()
            caller = ex.identity.resolve(token)
            if caller is None:
                raise ToolError(fixed("Unknown or missing credentials", "connect with a token the proxy's identity knows"))
            if tb.read:
                log({"tool": name, "caller": caller.actor.id, "args": args, "gated": False})
                res = upstream.call(name, args)
                if res.is_error:
                    raise ToolError(str(answer(res).get("result")))
                return answer(res)
            ikey = args.pop("idempotency_key", None) or hashlib.sha256(
                json.dumps([caller.actor.id, name, args], sort_keys=True, default=str).encode()).hexdigest()[:32]
            target = args.get(tb.new_id or tb.target or "")
            if target is None:
                raise ToolError(fixed(f"{name} needs `{tb.new_id or tb.target}`, the object it acts on",
                                      f"call it again with `{tb.new_id or tb.target}`"))
            action = ex.d.actions[tb.action]
            params = {p: args[arg] for p in action.params
                      if (arg := tb.params.get(p, p)) in args and args[arg] is not None}
            with gate:
                if tb.load:
                    load(name, tb, str(target), caller.actor.id)
                out = ex.submit(token, tb.action, str(target), params, f"proxy:{ikey}")
                log({"tool": name, "caller": caller.actor.id, "args": args, "gated": True, "action": tb.action,
                     "status": out.status, "code": out.code})
                if out.code == "in-progress":
                    raise ToolError(fixed(f"{name}: the same call is still running", "ask again in a moment"))
                if not out.ok:
                    raise ToolError(fixed(f"Refused by the declaration ({out.code}): {out.reason}",
                                          "if the declaration is wrong, a person changes it"))
                requested = [e for e in out.events if e.type == "EffectRequested"
                             and e.payload.get("service") == f"{UPSTREAM}{name}"]
                if not requested:
                    raise ToolError(fixed(f"{name}: {tb.action} was recorded, but calls nothing upstream",
                                          "check the declaration's effect for this action"))
                res = ex.store.read(f"{EFFECT_PREFIX}{effect_id(requested[0])}")
                if not res:                       # the outbox raised before it could answer
                    ex._dispatch_events(list(out.events))
                    res = ex.store.read(f"{EFFECT_PREFIX}{effect_id(requested[0])}")
                raw = services.last.pop(key(name, requested[0].payload.get("inputs") or {}), None)
            if not res:
                raise ToolError(fixed(f"{name} was allowed but not sent", "ask again; nothing was sent upstream"))
            result = res[0].payload.get("result") or {}
            if isinstance(raw, Exception):
                raise ToolError(fixed(f"{name}: the server did not answer ({type(raw).__name__}: {raw}); it may or may "
                                      "not have acted", "read the object upstream before you call again, then call "
                                      "with a new `idempotency_key`"))
            if res[0].type == "EffectFailed":
                why = (raw is not None and answer(raw).get("result")) or result.get("error") or res[0].payload.get("reason")
                raise ToolError(fixed(f"{name} failed upstream: {why}", "to try again, call with a new `idempotency_key`"))
            if raw is not None:
                return answer(raw)
            return {k: v for k, v in result.items() if k not in ("ok", "error")}   # answered before: as recorded

        # The upstream's own arguments, as they are; the upstream server validates them.
        fields = {f"a{i}": (Any, Field(None, alias=arg)) for i, arg in enumerate(schema.get("properties") or {})}
        model = create_model(f"{name}ProxyArgs", __base__=_StrictArgs, **fields)

        def proto() -> dict[str, Any]: ...    # only for the SDK to derive the output schema
        out = Tool.from_function(proto, name=name).fn_metadata

        def call(**kw: Any) -> dict[str, Any]:
            return fn(**{k: v for k, v in kw.items() if v is not None})

        return Tool(fn=call, name=name, description=str(up.description or name), parameters=schema,
                    fn_metadata=_RawArgs(arg_model=model, output_schema=out.output_schema,
                                         output_model=out.output_model, wrap_output=out.wrap_output),
                    is_async=False)

    return MCPServer(name=f"toprope-proxy:{ex.d.domain}",
                     instructions=(f"The tools of an existing server, under the Toprope declaration '{ex.d.domain}' "
                                   f"v{ex.d.version}: each call is checked against its rules before it is sent, "
                                   "and recorded."),
                     tools=[make(n, tb) for n, tb in binding.tools.items() if n in offered], **server_kwargs)


def confirm_binding(path: str | Path, caller: Any, at: str | None = None) -> str:
    """Record that `caller`, a person, confirmed the binding at `path` as it is now: `confirmed:
    {by, at, sha256}`, replacing any earlier record. Comments and layout are kept. Returns the
    hash. `toprope-proxy --confirm-binding` calls it once the binding would start."""
    import re
    from datetime import UTC, datetime

    from ..decl import load_yaml
    if caller.actor.kind != "person":
        raise SystemExit(fixed(f"{caller.actor.id} is an agent; only a person confirms a binding (ADR-0041)",
                               "ask the person the agent acts for to run it"))
    b = Binding.load(path)
    rec = {"by": caller.actor.id, "at": at or datetime.now(UTC).isoformat(timespec="seconds"), "sha256": b.digest}
    line = f"confirmed: {json.dumps(rec)}"
    text = Path(path).read_text()
    lines, skipping = [], False
    for ln in text.splitlines():                       # the earlier record, with any lines that continue it
        if re.match(r"^confirmed\s*:", ln):
            skipping = True
            continue
        if skipping and ln[:1] in (" ", "\t"):
            continue
        skipping = False
        lines.append(ln)
    at_upstream = next((i for i, ln in enumerate(lines) if re.match(r"^upstream\s*:", ln)), len(lines))
    lines.insert(at_upstream, line)
    new = "\n".join(lines) + "\n"
    after = load_yaml(new) or {}
    if after.get("confirmed") != rec or digest(after.get("upstream"), after.get("tools")) != b.digest:
        raise SystemExit(fixed(f"{path}: the confirmation could not be written so that it reads back",
                               "write `upstream:` and `tools:` as top-level keys, then confirm again"))
    Path(path).write_text(new)
    return b.digest


__all__ = ["Binding", "StoreLock", "ToolBinding", "Upstream", "UpstreamServices", "answer", "build_proxy", "check",
           "confirm_binding", "digest", "register"]
