"""OpenAPI 3 → things, facts, stages and actions (ADR-0049 A1a)."""
from __future__ import annotations

import json
import re
from typing import Any

import yaml

from . import TYPES, Candidate, Extraction, Profile, pascal, snake, stages


def _prop(spec: Any, optional: bool) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None
    if spec.get("enum"):
        return {"enum": [str(v) for v in spec["enum"]], "optional": optional}
    t = "datetime" if spec.get("format") == "date-time" else TYPES.get(str(spec.get("type")))
    return {"type": t, "optional": optional} if t else None


def _esc(seg: str) -> str:
    return seg.replace("~", "~0").replace("/", "~1")


def _refs(x: Any) -> set[str]:
    return {r.rsplit("/", 1)[-1] for r in re.findall(r'"\$ref": "([^"]+)"', json.dumps(x or {}))}


class OpenAPIExtractor:
    kind = "openapi"

    def extract(self, raw, profile: Profile) -> Extraction:
        doc = yaml.safe_load(raw.data) or {}
        ref, out = raw.ref, Extraction()
        schemas = ((doc.get("components") or {}).get("schemas")) or {}
        ops = [(path, m.lower(), op) for path, o in (doc.get("paths") or {}).items() for m, op in (o or {}).items()
               if isinstance(op, dict)]
        bodies = set().union(*[_refs(op.get("requestBody")) for _, _, op in ops]) if ops else set()
        used = set().union(*[_refs(op.get("responses")) for _, _, op in ops]) if ops else set()
        objects: dict[str, str] = {}
        for name, sch in schemas.items():
            if name in profile.ignore or not isinstance(sch, dict) or sch.get("type", "object") != "object" \
                    or not sch.get("properties") or (name in bodies and name not in used):
                continue
            obj = pascal(profile.name(name))
            req = set(sch.get("required") or [])
            props = {snake(p): x for p, s in sch["properties"].items() if p != "id" and (x := _prop(s, p not in req))}
            here = f"{ref}#/components/schemas/{_esc(name)}"
            out.candidates.append(Candidate(f"objects.{obj}", {"description": str(sch.get("description") or f"A {name}."),
                                                               "properties": props}, here))
            objects[obj] = next((p for p in props if p in profile.stage_fields and "enum" in props[p]), "")
            if objects[obj]:
                stages(out, obj, objects[obj], props[objects[obj]]["enum"], here)
        plural = {f"{o.lower()}s": o for o in objects} | {o.lower(): o for o in objects}
        for path, method, op in ops:
            if method not in ("post", "put", "patch", "delete"):
                continue
            segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
            target = next((plural[s.lower()] for s in segs if s.lower() in plural), None)
            source_name = op.get("operationId") or f"{method}_{'_'.join(segs)}"
            name = snake(profile.name(source_name))
            if source_name in profile.ignore or name in profile.ignore:      # by the source's name or ours
                continue
            body = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            if "$ref" in body:
                body = schemas.get(body["$ref"].rsplit("/", 1)[-1], {})
            req = set(body.get("required") or [])
            params = {snake(p): x for p, s in (body.get("properties") or {}).items() if (x := _prop(s, p not in req))}
            roles = op.get(profile.roles_from) if profile.roles_from else None
            creates = method == "post" and len(segs) == 1 and "{" not in path.rstrip("/").rsplit("/", 1)[-1]
            action = {"description": str(op.get("summary") or op.get("description") or name.replace("_", " ")).strip(),
                      "actor": list(roles) if isinstance(roles, list) and roles else list(profile.roles),
                      "params": params}
            if target:
                action["creates" if creates else "target"] = target
            here = f"{ref}#/paths/{_esc(path)}/{method}"
            out.candidates.append(Candidate(f"actions.{name}", action, here))
            if not (isinstance(roles, list) and roles):
                out.questions.append(f"Who may {action['description'].rstrip('.').lower()} ({name})?")
            if target and objects.get(target) and not creates:
                for c in [c for c in out.candidates if c.path == f"transitions.{target}"]:
                    for state in c.value["matrix"]:
                        out.candidates.append(Candidate(f"transitions.{target}.matrix.{state}.{name}", "undecided", here))
        return out

