"""An MCP server's tool list → proposed actions and a draft binding (ADR-0052 §7).

For each tool that changes something (not marked `readOnlyHint`):
- a proposed action, its params typed from the tool's input schema, acting on the thing an
  argument names (`order_id` → `Order`), with the effect `call: mcp:<tool>` passing every
  argument on (`with:`), and a reply;
- the reply action `record_<action>` (actor `external:kernel`): `ok` and the fields of the
  tool's output schema, refusing when the server did not do it, so a failure moves nothing;
- its cells, and the reply's, `undecided` in every stage: which stage moves is the person's.

A read-only tool becomes a read binding; one that takes the same id argument is guessed as the
tool that loads the thing (`load:`). The thing's facts come from that tool's output schema.

A tool whose arguments name no thing is not drafted and not bound, so the proxy never offers it;
a question says so. Everything is proposed: the questions name what a person decides (which
thing, which stage moves, who may call), and the binding is marked `status: proposed` until a
person confirms it (`toprope-proxy --confirm-binding`).
"""
from __future__ import annotations

import json
from typing import Any

import yaml

from . import (
    TYPES,
    Candidate,
    Extraction,
    Profile,
    a_,
    ignored,
    mapping,
    pascal,
    snake,
    stages,
)

VERBS = ("create_", "add_", "new_", "open_", "register_", "start_")


def _type(spec: Any, optional: bool) -> dict[str, Any] | None:
    """A JSON schema as a declared fact or param, or None when it is not a scalar."""
    if not isinstance(spec, dict):
        return None
    if isinstance(spec.get("anyOf"), list):                       # Optional[x] as the MCP SDK writes it
        rest = [s for s in spec["anyOf"] if not (isinstance(s, dict) and s.get("type") == "null")]
        if len(rest) != 1:
            return None
        return _type(rest[0], optional or len(rest) < len(spec["anyOf"]))
    types = spec.get("type")
    if isinstance(types, list):
        optional = optional or "null" in types
        rest = [t for t in types if t != "null"]
        types = rest[0] if len(rest) == 1 else None
    if spec.get("enum"):
        vals = list(dict.fromkeys(str(v) for v in spec["enum"] if v is not None))
        return {"enum": vals, "optional": optional} if vals else None
    t = "datetime" if spec.get("format") in ("date-time", "date") else TYPES.get(str(types))
    return {"type": t, "optional": optional} if t else None


def _id_arg(name: str, props: dict[str, Any]) -> tuple[str | None, list[str]]:
    """The argument that names the thing a tool acts on: `<thing>_id` (the one whose thing is in
    the tool's name, if several), or `id`. Returns it and every candidate."""
    ids = [a for a in props if a == "id" or a.endswith("_id")]
    named = [a for a in ids if a != "id" and a[:-3] in name]
    return (named or ids or [None])[0], ids


def _thing(arg: str, tool: str, profile: Profile) -> str:
    stem = arg[:-3] if arg.endswith("_id") else tool.split("_", 1)[-1]
    return pascal(profile.name(stem))


def _readonly(t: dict[str, Any]) -> bool:
    return (t.get("annotations") or {}).get("readOnlyHint") is True


class McpExtractor:
    kind = "mcp"

    def extract(self, raw, profile: Profile) -> Extraction:
        ref, out = raw.ref, Extraction()
        doc = mapping(yaml.safe_load(raw.data) or {}, ref, "an MCP tool list")
        tools = [t for t in doc.get("tools") or [] if isinstance(t, dict) and t.get("name")]
        server = doc.get("server") or {}
        bound: dict[str, dict[str, Any]] = {}
        notes: dict[str, list[str]] = {}
        unbound: dict[str, str] = {}
        loaders: dict[str, tuple[str, str, dict[str, Any], str]] = {}   # thing -> (tool, id arg, tool, place)
        actions: dict[str, tuple[str, dict[str, Any], str]] = {}         # action -> (thing, value, place)
        replies: dict[str, tuple[str, dict[str, Any], dict[str, str], str]] = {}
        for i, t in enumerate(tools):
            name, here = str(t["name"]), f"{ref}#/tools/{i}"
            props = (t.get("inputSchema") or {}).get("properties") or {}
            required = set((t.get("inputSchema") or {}).get("required") or [])
            if ignored(profile, name, snake(name)):
                unbound[name] = "left out by the profile"
                continue
            idarg, ids = _id_arg(name, props)
            if _readonly(t):
                bound[name] = {"read": True}
                notes[name] = ["the server marks it read-only (readOnlyHint): passed through, recorded, not gated"]
                if idarg:
                    loaders.setdefault(_thing(idarg, name, profile), (name, idarg, t, here))
                continue
            action = snake(profile.name(name))
            if idarg is None:
                unbound[name] = "none of its arguments names a thing it acts on"
                out.ask(f"Which thing does {name} act on? None of its arguments names one, so it was not drafted or "
                        "bound, and the proxy will not offer it: bind it to an action, or leave it out.", "target",
                        [f"actions.{action}"], [here])
                continue
            thing = _thing(idarg, name, profile)
            creates = name.startswith(VERBS)
            if len(ids) > 1:
                out.ask(f"Which thing does {name} act on: {', '.join(ids)} each name one; the draft guessed "
                        f"`{idarg}` ({thing}).", "target", [f"actions.{action}"], [here])
            params: dict[str, Any] = {}
            with_: dict[str, str] = {idarg: "target.id"}
            for arg, spec in props.items():
                if arg == idarg:
                    continue
                x = _type(spec, arg not in required)
                if x is None:
                    out.ask(f"{name}.{arg} is not a string, number or boolean, so the gate cannot check it"
                            + (" and the proxy will not start while the server requires it" if arg in required else
                               "; the proxy does not offer it") + ": leave it out, or which fact does it carry?",
                            "param", [f"actions.{action}.params"], [f"{here}/inputSchema/properties/{arg}"])
                    continue
                params[snake(arg)] = x
                with_[arg] = f"params.{snake(arg)}"
            reply = f"record_{action}"
            result = {f: x["type"] for f, s in ((t.get("outputSchema") or {}).get("properties") or {}).items()
                      if f not in ("ok", "error") and (x := _type(s, True)) and x.get("type")
                      and x["type"] in ("string", "integer", "number", "boolean")}
            if not (t.get("outputSchema") or {}).get("properties"):
                out.ask(f"What does {name} answer? It declares no output schema, so its reply ({f'record_{action}'}) "
                        "records only whether it succeeded: name the fields to keep (the binding's `result:` and the "
                        "reply's params).", "result", [f"actions.record_{action}.params"], [here])
            what = str(t.get("description") or name.replace("_", " ")).strip()
            actions[action] = (thing, {"description": what, "actor": list(profile.roles), "params": params,
                                       ("creates" if creates else "target"): thing,
                                       "effects": [{"call": f"mcp:{name}", "with": with_, "reply": reply}]}, here)
            replies[reply] = (thing, {
                "description": f"Record the server's answer to {name}.", "actor": ["external:kernel"], "target": thing,
                "params": {"ok": {"type": "boolean"}, **{f: {"type": ty, "optional": True} for f, ty in result.items()}},
                "preconditions": [{"id": f"{snake(name).replace('_', '-')}-done", "check": "params.ok == true",
                                   "reason": f"The server did not do it ({name})."}]}, result, here)
            bound[name] = {"action": action, ("new_id" if creates else "target"): idarg, "result": result}
            notes[name] = [f"guessed: `{idarg}` names {a_(thing)}" + (", and the tool creates it" if creates else "")]
            out.ask(f"Who may call {name}" + (f" ({action})?" if action != name else "?"), "actor",
                    [f"actions.{action}.actor"], [here])
        things = dict.fromkeys(thing for thing, _, _ in actions.values())
        for thing in things:
            loader = loaders.get(thing)
            facts: dict[str, Any] = {}
            place = loader[3] if loader else next(p for th, _, p in actions.values() if th == thing)
            if loader:
                for f, s in ((loader[2].get("outputSchema") or {}).get("properties") or {}).items():
                    req = set((loader[2].get("outputSchema") or {}).get("required") or [])
                    if f in ("id", loader[1]):
                        continue
                    if (x := _type(s, f not in req)) is not None:
                        facts[snake(f)] = x
            if not facts:
                out.ask(f"What facts does {a_(thing)} have, and which one is its stage? "
                        + (f"{loader[0]} declares no output schema." if loader else
                           "No read-only tool reads one."), "object", [f"objects.{thing}"], [place])
            out.candidates.append(Candidate(f"objects.{thing}", {
                "description": f"{a_(thing)[0].upper()}{a_(thing)[1:]}, as the server keeps it.", "properties": facts},
                place))
            mine = [a for a, (th, _, _) in actions.items() if th == thing]
            field = next((f for f in facts if f in profile.stage_fields and "enum" in facts[f]), None)
            if field:
                stages(out, thing, field, facts[field]["enum"], place)
                for a in mine:
                    for state in facts[field]["enum"]:
                        for x in (a, f"record_{a}"):
                            out.candidates.append(Candidate(f"transitions.{thing}.matrix.{state}.{x}", "undecided",
                                                            actions[a][2]))
                    out.ask(f"From which {field} may {a} be called, and which {field} does {a_(thing)} move to when "
                            f"the server has done it (record_{a})?", "cell",
                            [f"transitions.{thing}.matrix.{s}.{x}" for s in facts[field]["enum"]
                             for x in (a, f"record_{a}")], [actions[a][2]])
                out.ask(f"Which {field} does {a_(thing)} start in? The draft guessed {facts[field]['enum'][0]} (the first "
                        "the server lists).", "stage", [f"transitions.{thing}.initial"], [place])
            else:
                out.ask(f"Which fact of {a_(thing)} is its stage, and which stage do {', '.join(mine)} move it to?",
                        "stage", [f"transitions.{thing}"], [place])
            for a in mine:
                tool = actions[a][1]["effects"][0]["call"][4:]
                if loader and loader[1] in ((next(t for t in tools if t["name"] == loader[0]).get("inputSchema") or {})
                                            .get("properties") or {}) and loader[1] == bound[tool].get("target"):
                    bound[tool]["load"] = loader[0]
                    notes[tool].append(f"guessed: {loader[0]} reads {a_(thing)} by `{loader[1]}`, before every call")
                elif "target" in bound[tool]:
                    notes[tool].append(f"no read-only tool reads {a_(thing)} by `{bound[tool]['target']}`: the gate "
                                       "knows only what was recorded through it")
        for a, (thing, value, place) in actions.items():
            out.candidates.append(Candidate(f"actions.{a}", value, place))
        for r, (thing, value, result, place) in replies.items():
            facts = next((c.value["properties"] for c in out.candidates if c.path == f"objects.{thing}"), {})
            kept = {f"target.{snake(f)}": f"params.{f}" for f in result if snake(f) in facts}
            if kept:
                value["effects"] = [{"set": kept}]
            out.candidates.append(Candidate(f"actions.{r}", value, place))
        out.binding = {"upstream": server, "tools": bound, "notes": notes, "unbound": unbound, "source": ref}
        return out


def render_binding(b: dict[str, Any], domain: str) -> str:
    """The draft binding as YAML a person reads: every guess commented, `status: proposed`."""
    def flow(v: Any) -> str:
        return json.dumps(v, ensure_ascii=False)
    lines = [f"# A draft binding for {domain}, from the tool list of {b.get('source')} (toprope-import mcp).",
             "# Every guess is commented. Read it, change what is wrong, then confirm it as the person:",
             (f"#   toprope-proxy --confirm-binding --domain <{domain}'s declaration> --binding <this file> "
              "--identity ..."),
             "# The proxy will not start on a binding no person has confirmed (ADR-0041, ADR-0052 §7).",
             "status: proposed",
             f"upstream: {flow(b.get('upstream') or {})}",
             "tools:"]
    for tool, spec in (b.get("tools") or {}).items():
        lines.append(f"  {tool}:")
        for note in (b.get("notes") or {}).get(tool, []):
            lines.append(f"    # {note}")
        for k, v in spec.items():
            lines.append(f"    {k}: {flow(v)}")
    for tool, why in (b.get("unbound") or {}).items():
        lines.append(f"  # {tool}: not bound, so the proxy never offers it: {why}")
    return "\n".join(lines) + "\n"
