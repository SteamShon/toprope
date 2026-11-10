"""SQL DDL → enum facts and stages (ADR-0049 A1a).

Reads `CREATE TYPE … AS ENUM`, `CHECK (col IN (…))` (on a column or the table) and MySQL's
inline `ENUM(…)`. Names may be schema-qualified or quoted; comments are skipped, and every
citation keeps the line of its `CREATE TABLE`.
"""
from __future__ import annotations

import re

from . import (
    Candidate,
    Extraction,
    Profile,
    a_,
    ignored,
    pascal,
    put,
    singular,
    snake,
    stages,
)

NAME = r'(?:"[^"]+"|`[^`]+`|\[[^\]]+\]|\w+)'
QUALIFIED = rf"{NAME}(?:\s*\.\s*{NAME})*"
ENUM_TYPE = re.compile(rf"CREATE\s+TYPE\s+({QUALIFIED})\s+AS\s+ENUM\s*\(", re.IGNORECASE)
TABLE = re.compile(rf"CREATE\s+(?:(?:GLOBAL\s+|LOCAL\s+)?(?:TEMP|TEMPORARY)\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                   rf"({QUALIFIED})\s*\(", re.IGNORECASE)
CHECK_IN = re.compile(rf"CHECK\s*\(\s*({NAME})\s+IN\s*\(", re.IGNORECASE)
COLUMN = re.compile(rf"^\s*({NAME})\s+({QUALIFIED})(\s*\()?", re.IGNORECASE)
KEYWORDS = {"CHECK", "PRIMARY", "CONSTRAINT", "FOREIGN", "UNIQUE", "KEY", "INDEX", "EXCLUDE", "LIKE"}


def _last(qualified: str) -> str:
    """`public."Line Items"` → `Line Items`."""
    part = re.findall(NAME, qualified)[-1]
    return part[1:-1] if part[0] in "\"`[" else part


def _blank_comments(text: str) -> str:
    """Comments become spaces, keeping every newline so line numbers stay right."""
    def keep_lines(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return re.sub(r"/\*.*?\*/|--[^\n]*", keep_lines, text, flags=re.DOTALL)


def _inside(text: str, start: int) -> tuple[str, int]:
    """The text between the `(` just before `start` and its matching `)`, and where it ends."""
    depth, i, quote = 1, start, ""
    while i < len(text) and depth:
        ch = text[i]
        if quote:
            if ch == quote and text[i + 1:i + 2] == quote:    # '' inside a string
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    return text[start:i - 1], i


def _top_level(body: str) -> list[str]:
    """Split a table body at its top-level commas."""
    parts, depth, quote, cur = [], 0, "", []
    for ch in body:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    return [*parts, "".join(cur)]


def _values(text: str) -> list[str]:
    """`'a', 'it''s', 'b,c'` → ['a', "it's", 'b,c']; unquoted values (numbers) as written."""
    quoted = re.findall(r"'((?:[^']|'')*)'", text)
    vals = [v.replace("''", "'") for v in quoted] if quoted else [v.strip() for v in text.split(",") if v.strip()]
    return list(dict.fromkeys(vals))


class SQLExtractor:
    kind = "sql"

    def extract(self, raw, profile: Profile) -> Extraction:
        ref, out = raw.ref, Extraction()
        text = _blank_comments(raw.data.decode("utf-8", "replace"))
        enums = {_last(m.group(1)).lower(): _values(_inside(text, m.end())[0]) for m in ENUM_TYPE.finditer(text)}
        for t in TABLE.finditer(text):
            table = _last(t.group(1))
            body, _ = _inside(text, t.end())
            name = profile.name(table)
            obj = pascal(singular(name) if name == table else name)
            if ignored(profile, table, obj):
                continue
            here = f"{ref}#L{text.count(chr(10), 0, t.start()) + 1}"
            props: dict[str, dict] = {}
            checks: list[tuple[str, list[str]]] = []
            for item in _top_level(body):
                for ck in CHECK_IN.finditer(item):
                    checks.append((_last(ck.group(1)), _values(_inside(item, ck.end())[0])))
                c = COLUMN.match(item)
                if not c or _last(c.group(1)).upper() in KEYWORDS or _last(c.group(1)).lower() == "id":
                    continue
                col, typ = _last(c.group(1)), _last(c.group(2)).lower()
                optional = not re.search(r"\bNOT\s+NULL\b|\bPRIMARY\s+KEY\b", item, re.IGNORECASE)
                if typ == "enum" and c.group(3):                 # MySQL: status ENUM('a', 'b')
                    put(props, snake(col), {"enum": _values(_inside(item, c.end())[0]), "optional": optional}, out, here,
                        f"objects.{obj}.properties")
                elif typ in enums:
                    put(props, snake(col), {"enum": enums[typ], "optional": optional}, out, here, f"objects.{obj}.properties")
                for ck_col, vals in checks:
                    if ck_col.lower() == col.lower() and snake(col) not in props:
                        props[snake(col)] = {"enum": vals, "optional": optional}
            for ck_col, vals in checks:                          # table-level checks
                props.setdefault(snake(ck_col), {"enum": vals, "optional": False})
            if not props:
                continue
            out.candidates.append(Candidate(f"objects.{obj}", {"description": f"A row of {table}.", "properties": props}, here))
            field = next((p for p in props if p in profile.stage_fields), None)
            if field:
                stages(out, obj, field, props[field]["enum"], here)
                out.ask(f"What can be done to {a_(obj)} in each {field} ({', '.join(props[field]['enum'])})?", "cell",
                        [f"transitions.{obj}.matrix"], [here])
        return out
