"""Generate schema/domain.v1.schema.json and schema/representation.v1.schema.json.

The source of truth for the language is docs/domain-schema.md (ADR-0023). This file encodes
it for machines. Run: uv run python tools/gen_schema.py
"""
import json
from pathlib import Path

EXPR = {"type": "string", "description": "check-language expression (docs/domain-schema.md)"}
ID = {"type": "string", "pattern": r"^[A-Za-z_][A-Za-z0-9_-]*$"}
SCALAR_TYPES = ["string", "integer", "number", "boolean", "datetime"]


def obj(props, required=(), extra=False, **kw):
    return {"type": "object", "properties": props, "required": list(required),
            "additionalProperties": extra, **kw}


source = obj({"kind": {"enum": ["system", "record", "interview", "use"]},
              "ref": {"type": "string"}, "quote": {"type": "string"}}, ["kind"])
prov = {"source": {"$ref": "#/$defs/source"},
        "status": {"enum": ["proposed", "confirmed", "unknown"]}}


def with_prov(props, required=(), **kw):
    return obj({**props, **prov}, required, **kw)


typed = {"type": {"enum": SCALAR_TYPES}, "enum": {"type": "array", "items": {"type": "string"}},
         "ref": {"type": "string"}, "many": {"type": "boolean"}, "optional": {"type": "boolean"}}
property_ = obj({"type": {"enum": SCALAR_TYPES}, "enum": {"type": "array", "items": {"type": "string"}},
                 "optional": {"type": "boolean"}, "min": {"type": "number"}, "max": {"type": "number"}},
                oneOf=[{"required": ["type"]}, {"required": ["enum"]}])
param = obj(typed, oneOf=[{"required": ["type"]}, {"required": ["enum"]}, {"required": ["ref"]}])
deny = with_prov({"deny": {"type": "string"}}, ["deny"])
cell = {"oneOf": [
    {"type": "string"},  # target state | "n/a" | "undecided"
    deny,
    with_prov({"to": {"type": "string"}}, ["to"]),
    with_prov({"by_role": {"type": "object", "additionalProperties": {"oneOf": [{"type": "string"}, deny]}}},
              ["by_role"]),
]}
actor_rule = {"oneOf": [{"type": "string"}, obj({"role": {"type": "string"}, "where": EXPR}, ["role"])]}
effect = obj({"set": {"type": "object", "additionalProperties":
                      {"type": ["string", "number", "boolean", "null"]}},
              "create": {"type": "string", "description": "not supported yet (ADR-0021)"}})
precondition = with_prov({"id": ID, "check": EXPR, "reason": {"type": "string"}}, ["id", "check", "reason"])
action = with_prov({
    "description": {"type": "string"},
    "actor": {"type": "array", "items": actor_rule, "minItems": 1},
    "target": {"type": "string"}, "creates": {"type": "string"},
    "params": {"type": "object", "additionalProperties": param},
    "preconditions": {"type": "array", "items": precondition},
    "effects": {"type": "array", "items": effect},
    "records_decision": {"type": "boolean"},
    "event": {"type": "string"},
    "applies_in": {"type": "array", "items": {"type": "string"}},
    "requires": {"enum": ["human"]},
    "approvals": obj({"count": {"type": "integer", "minimum": 1}, "from_role": {"type": "string"},
                      "distinct": {"type": "boolean"}}, ["count", "from_role"]),
}, ["description", "actor"], oneOf=[{"required": ["target"]}, {"required": ["creates"]}])
duration = {"oneOf": [
    obj({"days": {"type": "number"}, "hours": {"type": "number"}, "minutes": {"type": "number"}},
        minProperties=1),
    obj({"field": {"type": "string"}, "unit": {"enum": ["days", "hours", "minutes"]}}, ["field", "unit"]),
]}
step = obj({
    "actor": {"type": "object"},
    "do": {"type": "string"}, "read": {"type": "object"}, "advance": duration["oneOf"][0],
    "target": {"type": "string"}, "params": {"type": "object"}, "expect": {"type": "object"},
}, oneOf=[{"required": ["do", "actor"]}, {"required": ["read", "actor"]}, {"required": ["advance"]}])

domain = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://toprope.dev/schema/domain.v1.schema.json",
    "title": "Toprope domain declaration v1 (docs/domain-schema.md, ADR-0023)",
    "$defs": {"source": source},
    **obj({
        "domain": ID, "version": {"type": "integer", "minimum": 1}, "owner": {"type": "string"},
        "purpose": obj({"problem": {"type": "string"},
                        "success_metric": obj({"name": {"type": "string"}, "definition": {"type": "string"},
                                               "direction": {"enum": ["up", "down"]}}, ["name", "direction"]),
                        "announcement": {"type": "string"}}, ["problem"]),
        "glossary": {"type": "object", "additionalProperties": {"type": "string"}},
        "roles": {"type": "array", "items": {"type": "string"}},
        "objects": {"type": "object", "additionalProperties": with_prov(
            {"description": {"type": "string"}, "properties": {"type": "object", "additionalProperties": property_}})},
        "links": {"type": "object", "additionalProperties": with_prov(
            {"from": {"type": "string"}, "to": {"type": "string"},
             "cardinality": {"enum": ["one-to-one", "one-to-many", "many-to-one", "many-to-many"]},
             "required": {"type": "boolean"}}, ["from", "to", "cardinality"])},
        "actions": {"type": "object", "additionalProperties": action},
        "transitions": {"type": "object", "additionalProperties": obj(
            {"field": {"type": "string"}, "initial": {"type": "string"},
             "matrix": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": cell}}},
            ["field", "matrix"])},
        "invariants": {"type": "array", "items": with_prov(
            {"id": ID, "on": {"type": "string"}, "check": EXPR, "reason": {"type": "string"},
             "scope": {"enum": ["aggregate", "cross"]}, "enforced_by": {"type": "string"}},
            ["id", "on", "check", "reason"])},
        "reservations": {"type": "object", "additionalProperties": obj(
            {"on": {"type": "string"}, "key": EXPR, "while_in": {"type": "array", "items": {"type": "string"}},
             "capacity": {"type": "integer", "minimum": 1}}, ["on", "key", "while_in"])},
        "timers": {"type": "object", "additionalProperties": obj(
            {"on": {"type": "string"}, "in_state": {"type": "string"}, "after": duration, "do": {"type": "string"}},
            ["on", "in_state", "after", "do"])},
        "functions": {"type": "object", "additionalProperties": obj(
            {"description": {"type": "string"}, "inputs": {"type": "object", "additionalProperties": param},
             "output": param, "examples": {"type": "array", "minItems": 1, "items": obj(
                 {"in": {"type": "object"}, "out": {}}, ["in", "out"])}},
            ["inputs", "output", "examples"])},
        "external": {"type": "object", "additionalProperties": obj(
            {"description": {"type": "string"}, "actions": {"type": "array", "items": {"type": "string"}}},
            ["actions"])},
        "handoffs": {"type": "object", "additionalProperties": obj(
            {"when": obj({"action": {"type": "string"}, "outcome": {"enum": ["ok"]}}, ["action"]),
             "to": obj({"domain": {"type": "string"}, "interface": {"type": "string"}, "action": {"type": "string"}},
                       ["domain", "interface", "action"]),
             "params": {"type": "object", "additionalProperties": EXPR}}, ["when", "to"])},
        "world": obj({"fixtures": {"type": "array", "items": {
            "type": "object", "minProperties": 1, "maxProperties": 1,
            "additionalProperties": obj({"id": {"type": "string"}}, ["id"], extra=True)}},
            "actors": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}}}),
        "scenarios": {"type": "array", "items": obj(
            {"id": ID, "given": {"type": "object"}, "steps": {"type": "array", "items": step, "minItems": 1}},
            ["id", "steps"])},
    }, ["domain", "version"]),
}

view_field_list = {"type": "array", "items": {"type": "string"}}
section = obj({"title": {"type": "string"}, "fields": view_field_list, "component": {"type": "string"}}, ["title"])
replace_or = lambda items: {"oneOf": [{"type": "array", "items": items}, obj({"replace": {"type": "array", "items": items}}, ["replace"])]}  # noqa: E731
views = {"type": "object", "additionalProperties": obj({
    "list": obj({"columns": replace_or({"type": "string"}), "group_by": {"type": "string"}, "sort": {"type": "string"}}),
    "detail": obj({"sections": replace_or(section), "actions": replace_or({"type": "string"})}),
    "board": obj({"by": {"type": "string"}}, ["by"]),
}, extra=True)}
representation = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://toprope.dev/schema/representation.v1.schema.json",
    "title": "Toprope representation and host overlay v1 (ADR-0008)",
    "oneOf": [
        obj({"representation": ID, "version": {"type": "integer"},
             "targets": obj({"domain": {"type": "string"}, "interface": {"type": "string"}}, ["domain", "interface"]),
             "views": views,
             "forms": {"type": "object", "additionalProperties": obj(
                 {"fields": view_field_list, "confirm": {"type": "string"}})},
             "aliases": {"type": "object", "additionalProperties": {"type": "string"}}},
            ["representation", "version", "targets"]),
        obj({"overlay": ID,
             "extends": obj({"representation": {"type": "string"}, "version": {"type": "string"}},
                            ["representation", "version"]),
             "targets": obj({"domain": {"type": "string"}, "interface": {"type": "string"}}, ["domain", "interface"]),
             "components": {"type": "object", "additionalProperties": obj(
                 {"package": {"type": "string"}, "props_from": view_field_list, "props": view_field_list})},
             "aliases": {"type": "object", "additionalProperties": {"type": "string"}},
             "views": views},
            ["overlay", "extends", "targets"]),
    ],
}

out = Path(__file__).resolve().parents[1] / "schema"
out.mkdir(exist_ok=True)
(out / "domain.v1.schema.json").write_text(json.dumps(domain, indent=2) + "\n")
(out / "representation.v1.schema.json").write_text(json.dumps(representation, indent=2) + "\n")
print("wrote", out / "domain.v1.schema.json", out / "representation.v1.schema.json")
