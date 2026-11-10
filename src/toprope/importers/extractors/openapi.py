"""OpenAPI 3 → things, facts, links, stages and actions (ADR-0049 A1a)."""
from __future__ import annotations

import json
import re
from typing import Any

import yaml

from . import (
    TYPES,
    Candidate,
    Extraction,
    Profile,
    a_,
    enum_fact,
    ignored,
    mapping,
    pascal,
    put,
    singular,
    snake,
    stages,
)


def _esc(seg: str) -> str:
    return seg.replace("~", "~0").replace("/", "~1")


def _refs(x: Any) -> set[str]:
    return {r.rsplit("/", 1)[-1] for r in re.findall(r'"\$ref": "([^"]+)"', json.dumps(x or {}))}


def _flat(sch: Any, schemas: dict[str, Any], seen: frozenset[str] = frozenset()) -> dict[str, Any]:
    """A schema with `$ref` and `allOf` resolved into one `properties` and `required`."""
    if not isinstance(sch, dict):
        return {}
    if "$ref" in sch:
        name = str(sch["$ref"]).rsplit("/", 1)[-1]
        return {} if name in seen else _flat(schemas.get(name), schemas, seen | {name})
    props, req = dict(sch.get("properties") or {}), set(sch.get("required") or [])
    for part in sch.get("allOf") or []:
        f = _flat(part, schemas, seen)
        props = {**f.get("properties", {}), **props}
        req |= set(f.get("required", []))
    return {**sch, "properties": props, "required": sorted(req)}


def _prop(spec: Any, optional: bool) -> dict[str, Any] | None:
    """A fact, or None when it is not one (a list, a nested thing, a reference)."""
    if not isinstance(spec, dict):
        return None
    types = spec.get("type")
    if isinstance(types, list):                                   # OpenAPI 3.1: [string, "null"]
        optional = optional or "null" in types
        rest = [t for t in types if t != "null"]
        types = rest[0] if len(rest) == 1 else None
    if spec.get("nullable"):
        optional = True
    if spec.get("enum"):
        return enum_fact(list(spec["enum"]), optional)
    t = "datetime" if spec.get("format") in ("date-time", "date") else TYPES.get(str(types))
    return {"type": t, "optional": optional} if t else None


class OpenAPIExtractor:
    kind = "openapi"

    def extract(self, raw, profile: Profile) -> Extraction:
        ref, out = raw.ref, Extraction()
        doc = mapping(yaml.safe_load(raw.data) or {}, ref, "an OpenAPI document")
        schemas = ((doc.get("components") or {}).get("schemas")) or {}
        ops = [(path, m.lower(), op) for path, o in (doc.get("paths") or {}).items() if isinstance(o, dict)
               for m, op in o.items() if isinstance(op, dict)]
        bodies = set().union(*[_refs(op.get("requestBody")) for _, _, op in ops]) if ops else set()
        used = set().union(*[_refs(op.get("responses")) for _, _, op in ops]) if ops else set()
        objects: dict[str, str] = {}                              # declared name -> its stage field ("" if none)
        by_source: dict[str, str] = {}                            # path words -> declared name
        refs_out: list[tuple[str, str, str, str]] = []           # (obj, fact, target schema, where)
        created: set[str] = set()
        obj_place: dict[str, str] = {}
        for name, sch in schemas.items():
            sch = _flat(sch, schemas)
            obj = pascal(profile.name(name))
            if ignored(profile, name, obj) or sch.get("type", "object") != "object" or not sch.get("properties") \
                    or (name in bodies and name not in used):
                continue
            req = set(sch.get("required") or [])
            here = f"{ref}#/components/schemas/{_esc(name)}"
            props: dict[str, Any] = {}
            for p, s in sch["properties"].items():
                if p == "id":
                    continue
                if isinstance(s, dict) and "$ref" in s:
                    refs_out.append((obj, snake(p), str(s["$ref"]).rsplit("/", 1)[-1], here))
                elif (x := _prop(s, p not in req)) is not None:
                    put(props, snake(p), x, out, here, f"objects.{obj}.properties")
                else:
                    out.ask(f"{name}.{p} is a list or a nested shape: which thing holds it, if any?", "nested",
                            [f"objects.{obj}.properties.{snake(p)}"], [f"{here}/properties/{_esc(p)}"])
            out.candidates.append(Candidate(f"objects.{obj}", {"description": str(sch.get("description") or f"A {name}."),
                                                               "properties": props}, here))
            objects[obj] = next((p for p in props if p in profile.stage_fields and "enum" in props[p]), "")
            obj_place.setdefault(obj, here)
            if objects[obj]:
                stages(out, obj, objects[obj], props[objects[obj]]["enum"], here)
            for word in (name, singular(name), f"{name}s", snake(name), f"{snake(name)}s"):
                by_source.setdefault(word.lower(), obj)
        for obj, fact, target, here in refs_out:
            if (to := by_source.get(target.lower())) in objects:
                out.candidates.append(Candidate(f"links.{snake(obj)}_{fact}", {"from": obj, "to": to,
                                                                              "cardinality": "many-to-one"}, here))
        for path, method, op in ops:
            if method not in ("post", "put", "patch", "delete"):
                continue
            segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
            target = next((by_source[s.lower()] for s in segs if s.lower() in by_source), None)
            source_name = op.get("operationId") or f"{method}_{'_'.join(segs)}"
            name = snake(profile.name(source_name))
            if ignored(profile, source_name, name):
                continue
            here = f"{ref}#/paths/{_esc(path)}/{method}"
            if target is None:
                out.ask(f"Which thing does {name} ({method.upper()} {path}) act on? The source names "
                        "none it describes, so it was left out.", "target", [f"actions.{name}"], [here])
                continue
            body = _flat((((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {})
                         .get("schema") or {}, schemas)
            req = set(body.get("required") or [])
            params: dict[str, Any] = {}
            for p, s in (body.get("properties") or {}).items():
                if (x := _prop(s, p not in req)) is not None:
                    put(params, snake(p), x, out, here, f"actions.{name}.params")
            roles = op.get(profile.roles_from) if profile.roles_from else None
            roles = [roles] if isinstance(roles, str) else roles
            creates = method == "post" and len(segs) == 1 and "{" not in path.rstrip("/").rsplit("/", 1)[-1]
            action = {"description": str(op.get("summary") or op.get("description") or name.replace("_", " ")).strip(),
                      "actor": [str(r) for r in roles] if isinstance(roles, list) and roles else list(profile.roles),
                      "params": params, ("creates" if creates else "target"): target}
            call = op.get("x-toprope-call") or (profile.options.get("calls") or {}).get(source_name) \
                or (profile.options.get("calls") or {}).get(name)
            reply = f"record_{name}"
            if call:                                              # a known call target: the effect and its reply
                ids = [s[1:-1] for s in path.strip("/").split("/") if s.startswith("{") and s.endswith("}")]
                with_ = {**({ids[-1]: "target.id"} if ids and not creates else {}),
                         **{p: f"params.{p}" for p in params}}
                action["effects"] = [{"call": str(call), "with": with_, "reply": reply}]
                out.candidates.append(Candidate(f"actions.{reply}", {
                    "description": f"Record the answer to {name}.", "actor": ["external:kernel"], "target": target,
                    "params": {"ok": {"type": "boolean"}},
                    "preconditions": [{"id": f"{name.replace('_', '-')}-done", "check": "params.ok == true",
                                       "reason": f"The call behind {name} did not succeed."}]}, here))
            else:
                out.ask(f"What carries out {name} once it is allowed? The source names no call, so the draft has no "
                        "effect: name the tool (`call: mcp:<tool>`, with a reply action), or say it changes only "
                        "Toprope's record.", "call", [f"actions.{name}.effects"], [here])
            out.candidates.append(Candidate(f"actions.{name}", action, here))
            if creates:
                created.add(target)
            if not (isinstance(roles, list) and roles):
                out.ask(f"Who may {action['description'].rstrip('.').lower()} ({name})?", "actor",
                        [f"actions.{name}.actor"], [here])
            if objects.get(target) and not creates:
                for c in [c for c in out.candidates if c.path == f"transitions.{target}"]:
                    for state in c.value["matrix"]:
                        for x in (name, reply) if call else (name,):
                            out.candidates.append(Candidate(f"transitions.{target}.matrix.{state}.{x}", "undecided",
                                                            here))
        for obj in objects:
            if obj not in created:
                out.ask(f"How is {a_(obj)} created? No operation in the source creates one: name the action that does "
                        "(and who may take it), or say it comes from elsewhere (another system, an import).",
                        "creation", [f"objects.{obj}", "actions"], [obj_place[obj]])
        return out
