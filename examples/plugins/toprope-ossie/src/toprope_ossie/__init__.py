"""An extractor for Apache Ossie ontologies, plugged into Toprope from outside (ADR-0051).

It uses only Toprope's public port (`toprope.importers`) and registers through the entry-point
group `toprope.extractors` (see this package's `pyproject.toml`), so Toprope does not change
when it is installed. Any tool that exports Ossie can feed it, for example NVIDIA Auto Ontology
(*Settings → Import / Export*, Apache Ossie with the ontology) or the converters in
apache/ossie-converters.

What an Ossie ontology says, and what it becomes:

- an `EntityType` concept → a thing (`objects.<Concept>`);
- a relationship from it to a value type or a built-in → a fact, typed by the built-in the value
  type extends; `X == 'a' OR X == 'b'` on the value type → an enum; `X >= 0`, `X <= 9` → min, max;
- a relationship with no other role (`canceled`) → a boolean fact;
- a relationship to another entity type → a link, `ManyToOne` → many-to-one, `OneToOne` →
  one-to-one;
- a fact is required when the concept identifies by it or `requires: [Concept.fact]`; otherwise it
  is optional, as in Ossie;
- an enum fact named in the profile's `stage_fields` → stages, for the interview to fill.

What it cannot say becomes a question: what happens to the things (Ossie has no actions), who may
do it, and every constraint it does not translate (`derived_by`, other `requires`, relationships
of three or more roles). Every element stays `proposed` until a person confirms it.
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

        def value_type(name: str, seen: frozenset[str] = frozenset()) -> tuple[str | None, list[str]]:
            """The built-in a value type extends, and the constraints on the way there."""
            if name in BUILTINS:
                return BUILTINS[name], []
            if name not in by_name or name in seen or by_name[name][1].get("type") != "ValueType":
                return None, []
            c = by_name[name][1]
            reqs = [(name, r) for r in c.get("requires") or []]
            for sup in c.get("extends") or []:
                t, more = value_type(sup, seen | {name})
                if t:
                    return t, reqs + more
            return None, reqs

        things: list[str] = []
        for name, (i, c) in by_name.items():
            if c.get("type") != "EntityType" or name in profile.ignore:
                continue
            obj = _pascal(profile.name(name))
            ref = f"{raw.ref}#/ontology/{i}"
            props: dict[str, Any] = {}
            ident = set(c.get("identify_by") or [])
            required = {m.group(1) for r in c.get("requires") or []
                        if isinstance(r, str) and (m := re.fullmatch(rf"{re.escape(name)}\.(\w+)", r.strip()))}
            for r in c.get("requires") or []:
                if not (isinstance(r, str) and re.fullmatch(rf"{re.escape(name)}\.(\w+)", r.strip())):
                    out.questions.append(f"The source requires `{r}` of every {name}. Is that a rule to enforce?")
            for sup in c.get("extends") or []:
                out.questions.append(f"The source says every {name} is also a {sup}. Which of {sup}'s facts "
                                     f"does {obj} need?")
            for j, rel in enumerate(c.get("relationships") or []):
                rname, rref = rel.get("name", ""), f"{ref}/relationships/{j}"
                fact = _snake(rname)
                roles = [ro.get("concept") for ro in rel.get("roles") or []]
                if rel.get("derived_by"):
                    out.questions.append(f"{name}.{rname} is derived ({'; '.join(rel['derived_by'])}). A "
                                         "declaration keeps facts, not reports: leave it out, or keep it as a fact?")
                    continue
                for r in rel.get("requires") or []:
                    out.questions.append(f"The source requires `{r}` of {name}.{rname}. Is that a rule to enforce?")
                if len(roles) > 1:
                    out.questions.append(f"{name}.{rname} relates {name} to {', '.join(map(str, roles))} at once. "
                                         "Which thing should hold it?")
                    continue
                if not roles:                                    # a unary fact: true or false
                    props[fact] = {"type": "boolean"}
                    continue
                target = roles[0]
                if target in by_name and by_name[target][1].get("type") == "EntityType":
                    if target in profile.ignore:
                        continue
                    out.candidates.append(Candidate(f"links.{_snake(obj)}_{fact}", {
                        "from": obj, "to": _pascal(profile.name(target)),
                        "cardinality": CARDINALITY.get(rel.get("multiplicity"), "many-to-many"),
                        "required": rname in ident or rname in required}, rref))
                    continue
                t, reqs = value_type(target)
                if t is None:
                    out.conflicts.append(f"{name}.{rname} ({rref}) names {target}, which the source does not "
                                         "declare as a value type; read as text")
                    t = "string"
                p: dict[str, Any] = {"type": t}
                for vt, expr in reqs:
                    if (vals := _enum(expr, vt)) is not None:
                        p = {"enum": vals}
                    elif (b := _bound(expr, vt)) is not None and t in ("integer", "number"):
                        p[b[0]] = b[1]
                    else:
                        out.questions.append(f"The source requires `{expr}` of {vt} ({name}.{rname}). Is that a "
                                             "rule to enforce?")
                if rname not in ident and rname not in required:
                    p["optional"] = True
                props[fact] = p
            value: dict[str, Any] = {"properties": props}
            if c.get("description"):
                value["description"] = c["description"]
            out.candidates.append(Candidate(f"objects.{obj}", value, ref))
            for fact, p in props.items():
                if fact in profile.stage_fields and p.get("enum"):
                    out.candidates.append(Candidate(f"transitions.{obj}", {
                        "field": fact, "initial": p["enum"][0], "matrix": {s: {} for s in p["enum"]}}, ref))
                    out.questions.append(f"Which {fact} does a new {obj} start in, and what moves it on?")
            things.append(obj)
        if things:
            out.questions.append(f"What happens to {', '.join(things)}, and who may do it? (Ossie describes things, "
                                 "not actions)")
        return out

