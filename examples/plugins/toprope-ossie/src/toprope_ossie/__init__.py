"""An extractor for Apache Ossie ontologies, plugged into Toprope from outside (ADR-0051).

It uses only Toprope's public port (`toprope.importers`) and registers through the entry-point
group `toprope.extractors` (see this package's `pyproject.toml`), so Toprope does not change
when it is installed. Any tool that exports Ossie can feed it, for example NVIDIA Auto Ontology
(*Settings → Import / Export*, Apache Ossie with the ontology) or the converters in
apache/ossie-converters.

What an Ossie ontology says, and what it becomes:

- an `EntityType` concept → a thing (`objects.<Concept>`);
- a relationship from it to a value type or a built-in → a fact, typed by the built-in the value
  type extends; `X == 'a' OR X == 'b'` on a string value type → an enum; `X >= 0`, `X <= 9` →
  min, max; limits on a value type and its supertypes all hold, so the tightest wins;
- a relationship with no other role (`canceled`) → a boolean fact;
- a relationship to another entity type → a link, `ManyToOne` → many-to-one, `OneToOne` →
  one-to-one;
- a fact is required when the concept identifies by it or `requires: [Concept.fact]`; otherwise it
  is optional, as in Ossie; a fact with no multiplicity may have many values, so it is asked about;
- an enum fact named in the profile's `stage_fields` → stages, for the interview to fill.

What it cannot say becomes a question: what happens to the things (Ossie has no actions), who may
do it, and everything it does not translate (`derived_by` on a concept or a relationship, other
`requires`, relationships of three or more roles, links to ignored concepts). Two source names
that read as one name are a conflict. Every element stays `proposed` until a person confirms it.
"""
from __future__ import annotations

import re
from typing import Any

import yaml

from toprope.errors import fixed
from toprope.importers import Candidate, Extraction, Profile, Raw

BUILTINS = {"String": "string", "Integer": "integer", "Decimal": "number", "Float": "number",
            "Boolean": "boolean", "Date": "datetime", "DateTime": "datetime"}
CARDINALITY = {"ManyToOne": "many-to-one", "OneToOne": "one-to-one"}


def _snake(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)).strip("_").lower()
    return s if s and s[0].isalpha() else f"x_{s}"


def _pascal(name: str) -> str:
    s = "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", name) if w)
    return s if s and s[0].isalpha() else f"X{s}"


def _enum(expr: str, name: str) -> list[str] | None:
    """`X == 'A' OR X == 'B'` → ['A', 'B']; anything else → None."""
    parts = re.split(r"\s+OR\s+", expr.strip())
    vals = [m.group(1) for p in parts if (m := re.fullmatch(rf"{re.escape(name)}\s*==\s*'([^']*)'", p.strip()))]
    return vals if len(vals) == len(parts) else None


def _bound(expr: str, name: str) -> tuple[str, float] | None:
    """`X >= 0`, `X <= 9`, `0 <= X`, `9 >= X` → ('min', 0.0) or ('max', 9.0)."""
    n, num = re.escape(name), r"(-?\d+(?:\.\d+)?)"
    for pat, kind in ((rf"{n}\s*>=\s*{num}", "min"), (rf"{num}\s*<=\s*{n}", "min"),
                      (rf"{n}\s*<=\s*{num}", "max"), (rf"{num}\s*>=\s*{n}", "max")):
        if m := re.fullmatch(pat, expr.strip()):
            return kind, float(m.group(1))
    return None


class OssieExtractor:
    kind = "ossie"

    def extract(self, raw: Raw, profile: Profile) -> Extraction:
        out = Extraction()
        try:
            doc = yaml.safe_load(raw.data) or {}
        except yaml.YAMLError as e:
            raise SystemExit(fixed(f"{raw.ref} is not YAML: {e}", "give an Ossie ontology document")) from None
        concepts = doc.get("ontology") if isinstance(doc, dict) else None
        if not isinstance(concepts, list):
            raise SystemExit(fixed(f"{raw.ref} has no `ontology` list", "give the Ossie ontology document, not the "
                                   "semantic model (Auto Ontology: export Apache Ossie with the ontology)"))
        by_name = {c["concept"]: (i, c) for i, c in enumerate(concepts) if isinstance(c, dict) and "concept" in c}
        for e in doc.get("requires") or []:
            out.questions.append(f"The source requires `{e}` of the whole model. Is that a rule to enforce?")

        def kind_of(name: str) -> str | None:
            return "EntityType" if name == "Any" else by_name.get(name, (0, {}))[1].get("type")

        def value_type(name: str, seen: frozenset[str] = frozenset()) -> tuple[str | None, list[tuple[str, str]], str]:
            """The built-in a value type extends, the constraints on the way there, and why not if not."""
            if name in BUILTINS:
                return BUILTINS[name], [], ""
            if name in seen:
                return None, [], f"its value types extend each other in a cycle ({' → '.join([*seen, name])})"
            if kind_of(name) != "ValueType":
                return None, [], "the source does not declare it as a value type"
            c = by_name[name][1]
            reqs = [(name, r) for r in c.get("requires") or [] if isinstance(r, str)]
            why = "it extends no built-in"
            for sup in c.get("extends") or []:
                t, more, why = value_type(sup, seen | {name})
                if t:
                    return t, reqs + more, ""
            return None, reqs, why

        def fact(owner: str, rname: str, target: str, rref: str, required: bool) -> dict[str, Any] | None:
            t, reqs, why = value_type(target)
            if t is None:
                out.conflicts.append(f"{owner}.{rname} ({rref}) names {target}, but {why}; read as text")
                t, reqs = "string", []
            enum: list[str] | None = None
            lo, hi = None, None
            for vt, expr in reqs:
                if t == "string" and (vals := _enum(expr, vt)) is not None:
                    vals = list(dict.fromkeys(vals))
                    enum = vals if enum is None else [v for v in enum if v in vals]      # every limit holds
                elif t in ("integer", "number") and (b := _bound(expr, vt)) is not None:
                    lo = max(lo, b[1]) if b[0] == "min" and lo is not None else (b[1] if b[0] == "min" else lo)
                    hi = min(hi, b[1]) if b[0] == "max" and hi is not None else (b[1] if b[0] == "max" else hi)
                else:
                    out.questions.append(f"The source requires `{expr}` of {vt} ({owner}.{rname}). Is that a rule "
                                         "to enforce?")
            if enum is not None and not enum:
                out.conflicts.append(f"{owner}.{rname} ({rref}): the limits on {target} leave no value; read as text")
                enum = None
            p: dict[str, Any] = {"enum": enum} if enum is not None else {"type": t}
            if enum is None and lo is not None:
                p["min"] = lo
            if enum is None and hi is not None:
                p["max"] = hi
            if not required:
                p["optional"] = True
            return p

        things: list[str] = []
        for name, (i, c) in by_name.items():
            ref = f"{raw.ref}#/ontology/{i}"
            if c.get("type") == "ValueType" and c.get("relationships"):
                out.questions.append(f"The value type {name} ({ref}) has relationships of its own: which thing "
                                     "should hold them?")
            if c.get("type") != "EntityType":
                continue
            obj = _pascal(profile.name(name))
            if name in profile.ignore or obj in profile.ignore:
                continue
            if c.get("derived_by"):
                out.questions.append(f"{name} is derived ({'; '.join(map(str, c['derived_by']))}): keep it as a thing "
                                     "of its own? It was left out.")
                continue
            rels = [r for r in c.get("relationships") or [] if isinstance(r, dict)]
            rel_names = {r.get("name") for r in rels}
            ident = set(c.get("identify_by") or [])
            required = set()
            for r in c.get("requires") or []:
                m = re.fullmatch(rf"{re.escape(name)}\.(\w+)", r.strip()) if isinstance(r, str) else None
                if m and m.group(1) in rel_names:
                    required.add(m.group(1))
                elif m:
                    out.conflicts.append(f"{ref} requires {r}, but {name} has no relationship {m.group(1)}")
                else:
                    out.questions.append(f"The source requires `{r}` of every {name}. Is that a rule to enforce?")
            for sup in c.get("extends") or []:
                out.questions.append(f"The source says every {name} is also a {sup}. Which of {sup}'s facts "
                                     f"does {obj} need?")
            props: dict[str, Any] = {}
            for j, rel in enumerate(c.get("relationships") or []):
                if not isinstance(rel, dict):
                    continue
                rname, rref = str(rel.get("name", "")), f"{ref}/relationships/{j}"
                key = _snake(rname)
                roles = rel.get("roles") or []
                if not all(isinstance(ro, dict) and ro.get("concept") for ro in roles):
                    raise SystemExit(fixed(f"{rref}: a role of {name}.{rname} is not `{{concept: Name}}`",
                                           "write each role as a mapping with a `concept`"))
                roles = [ro["concept"] for ro in roles]
                if rel.get("derived_by"):
                    out.questions.append(f"{name}.{rname} is derived ({'; '.join(map(str, rel['derived_by']))}). A "
                                         "declaration keeps facts, not reports: leave it out, or keep it as a fact?")
                    continue
                for r in rel.get("requires") or []:
                    out.questions.append(f"The source requires `{r}` of {name}.{rname}. Is that a rule to enforce?")
                if len(roles) > 1:
                    out.questions.append(f"{name}.{rname} relates {name} to {', '.join(map(str, roles))} at once. "
                                         "Which thing should hold it?")
                    continue
                must = rname in ident or rname in required
                if not roles:                                    # a unary fact: true or false
                    value: dict[str, Any] | None = {"type": "boolean"}
                elif kind_of(roles[0]) == "EntityType":
                    target = roles[0]
                    if target == "Any" or target in profile.ignore or _pascal(profile.name(target)) in profile.ignore:
                        out.questions.append(f"{name}.{rname} ({rref}) links to {target}, which "
                                             f"{'names no thing' if target == 'Any' else 'the profile ignores'}"
                                             f"{'; it identifies a ' + name if rname in ident else ''}: it was left out.")
                        continue
                    out.candidates.append(Candidate(f"links.{_snake(obj)}_{key}", {
                        "from": obj, "to": _pascal(profile.name(target)),
                        "cardinality": CARDINALITY.get(rel.get("multiplicity"), "many-to-many"), "required": must}, rref))
                    continue
                elif rel.get("multiplicity") not in CARDINALITY:
                    out.questions.append(f"Can {_a(name)} have more than one {rname}? The source gives no multiplicity, "
                                         f"so {name}.{rname} was left out.")
                    continue
                else:
                    value = fact(name, rname, roles[0], rref, must)
                if key in props:
                    out.conflicts.append(f"{rref}: {name}.{rname} reads as `{key}`, like another fact; kept the first")
                    continue
                props[key] = value
            item: dict[str, Any] = {"properties": props}
            if c.get("description"):
                item["description"] = c["description"]
            out.candidates.append(Candidate(f"objects.{obj}", item, ref))
            for key, p in props.items():
                src = next((str(r.get("name")) for r in rels if _snake(str(r.get("name"))) == key), key)
                if (src in profile.stage_fields or key in profile.stage_fields) and p.get("enum"):
                    out.candidates.append(Candidate(f"transitions.{obj}", {
                        "field": key, "initial": p["enum"][0], "matrix": {s: {} for s in p["enum"]}}, ref))
                    out.questions.append(f"Which {key} does a new {obj} start in (the draft says {p['enum'][0]}), and "
                                         "what moves it on?")
                    break
            if obj not in things:
                things.append(obj)
        if things:
            out.questions.append(f"What happens to {', '.join(things)}, and who may do it? (Ossie describes things, "
                                 "not actions)")
        return out


def _a(w: str) -> str:
    return f"{'an' if w[:1].lower() in 'aeiou' else 'a'} {w}"
