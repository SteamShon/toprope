"""SQL DDL → enum facts and stages (ADR-0049 A1a)."""
from __future__ import annotations

import re

from . import Candidate, Extraction, Profile, a_, pascal, snake, stages

ENUM_TYPE = re.compile(r"CREATE\s+TYPE\s+(\w+)\s+AS\s+ENUM\s*\(([^)]*)\)", re.IGNORECASE)
TABLE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)[\"`]?\s*\((.*?)\)\s*;", re.IGNORECASE | re.DOTALL)
CHECK_IN = re.compile(r"CHECK\s*\(\s*[\"`]?(\w+)[\"`]?\s+IN\s*\(([^)]*)\)\s*\)", re.IGNORECASE)
COLUMN = re.compile(r"^\s*[\"`]?(\w+)[\"`]?\s+(\w+)")
KEYWORDS = {"CHECK", "PRIMARY", "CONSTRAINT", "FOREIGN", "UNIQUE"}


def _values(text: str) -> list[str]:
    return [v.strip().strip("'\"") for v in text.split(",") if v.strip()]


class SQLExtractor:
    kind = "sql"

    def extract(self, raw, profile: Profile) -> Extraction:
        text, ref, out = raw.data.decode("utf-8", "replace"), raw.ref, Extraction()
        enums = {m.group(1).lower(): _values(m.group(2)) for m in ENUM_TYPE.finditer(text)}
        for t in TABLE.finditer(text):
            table, body = t.group(1), t.group(2)
            if table in profile.ignore:
                continue
            line = text.count("\n", 0, t.start()) + 1
            name = profile.name(table)
            obj = pascal(name[:-1] if name.endswith("s") and name == table else name)
            props = {}
            for row in body.splitlines():
                c = COLUMN.match(row)
                if not c or c.group(1).upper() in KEYWORDS or c.group(1).lower() == "id":
                    continue
                col, typ, optional = c.group(1), c.group(2).lower(), "not null" not in row.lower()
                if typ in enums:
                    props[snake(col)] = {"enum": enums[typ], "optional": optional}
                if (ck := CHECK_IN.search(row)) and ck.group(1).lower() == col.lower():
                    props[snake(col)] = {"enum": _values(ck.group(2)), "optional": optional}
            for ck in CHECK_IN.finditer(body):
                props.setdefault(snake(ck.group(1)), {"enum": _values(ck.group(2)), "optional": False})
            if not props:
                continue
            here = f"{ref}#L{line}"
            out.candidates.append(Candidate(f"objects.{obj}", {"description": f"A row of {table}.", "properties": props}, here))
            field = next((p for p in props if p in profile.stage_fields), None)
            if field:
                stages(out, obj, field, props[field]["enum"], here)
                out.questions.append(f"What can be done to {a_(obj)} in each {field} ({', '.join(props[field]['enum'])})?")
        return out

