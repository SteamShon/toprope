"""`toprope-interview`: the interview, in your terminal, on your own domain (ADR-0053 §2).

    toprope-interview                      # the domain in this directory (domain.yaml)
    toprope-interview my-approvals         # a directory toprope-init wrote, or any with a domain.yaml
    toprope-interview DIR --answers FILE   # the same, answers read from FILE, one per line
    toprope-interview DIR --share          # how many rule questions offered a recommended choice

It asks one question at a time, in the order the declaration depends on (ADR-0025): sources,
purpose, people and things, actions, stages, rules, examples, review. Where the answer becomes a
rule (who may take an action, what must be true first, an outcome rule, what an action does in each
stage), it offers numbered choices built from your examples and your sources, one recommended with
why. Press Enter for the recommended one, type its number for another, or type your own answer.

Everything it writes is `proposed`. Nothing is enforced until you confirm it: at the end it shows
every proposed element and what approving it decides, and confirms only when you type `yes`.

A directory without `toprope.workspace.yaml` gets one: the declaration is `domain.yaml`, the
interview log `interview/log.jsonl`, and a `sources/` folder, if there is one, is read as your
sources (its Markdown files). With `--answers FILE` (or answers piped on stdin), each line answers
the next question; an empty line takes the recommended choice; a line starting with `#` is skipped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

import yaml

from ...errors import fixed

CONFIG = "toprope.workspace.yaml"
NONE = {"none", "nothing", "no", "-", "n/a"}
TYPES = {"number": {"type": "number"}, "decimal": {"type": "number"}, "integer": {"type": "integer"},
         "whole number": {"type": "integer"}, "count": {"type": "integer"}, "text": {"type": "string"},
         "string": {"type": "string"}, "yes/no": {"type": "boolean"}, "boolean": {"type": "boolean"},
         "date": {"type": "datetime"}, "datetime": {"type": "datetime"}, "time": {"type": "datetime"}}
HINTS = {
    "sources": "paths in this directory, separated by commas (Enter or `none`: no sources)",
    "purpose:problem": "a sentence or two",
    "purpose:metric": "the metric, then `up` or `down`: e.g. `requests decided within a day, up`",
    "purpose:announcement": "two sentences",
    "cast:roles": "`role: what they do; role: what they do`",
    "cast:objects": "`Thing: what it is | fact: type, fact: type; ...` (types: number, integer, text, yes/no, "
                    "date, or choices like `low/high`)",
    "cast:links": "`Thing -> Other many-to-one; ...` (one-to-one, one-to-many, many-to-one, many-to-many; "
                  "add `required` if it must be set)",
    "example": "`ID: fact value, fact value`, e.g. `LR-7: days 12`",
    "actions": "`name: what it does -> Thing; name: what it does -> new Thing` (`new`: it makes the thing)",
    "transitions": "`field: stage, stage, stage; starts stage`",
    "invariants": "a number to choose, or your own rule: `check | why`",
    "default": "a number to choose, or `from STAGE to STAGE`",
    "limit": "a number to choose, or `over N`, `over N, only ROLE`, `<fact> over N, only ROLE`",
    "world:fixtures": "`Thing ID: fact value, fact value; ...`",
    "world:actors": "`role: name, name; role: name`",
    "world:scenarios": "`role action ID [fact=value] -> stage|refused [code]; ...`",
    "review:glossary": "`term: what it means; term: what it means`",
}


class Stop(Exception):
    """The answers ran out, or the person stopped."""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-interview", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?", default=".", help="the domain's directory (default: here); it holds domain.yaml, "
                    "or the interview starts one")
    ap.add_argument("--answers", help="read the answers from this file, one per line, instead of the terminal")
    ap.add_argument("--share", action="store_true", help="print ADR-0053's choice measure from the interview log and stop")
    return ap


# -- the workspace -----------------------------------------------------------------------------
def open_workspace(where: Path):
    from ...workspace import Workspace
    if not where.is_dir():
        raise SystemExit(fixed(f"no directory {where}", "give the domain's directory, such as one `toprope-init` wrote"))
    cfg = where / CONFIG
    if not cfg.exists():
        sources: list[dict[str, Any]] = [{"id": "interview", "kind": "interview-log", "path": "interview/log.jsonl"}]
        if (where / "sources").is_dir():
            sources.insert(0, {"id": "sources", "kind": "records", "path": "sources"})
        cfg.write_text("# The interview's workspace (toprope-interview): the declaration, the log, the sources.\n" +
                       yaml.safe_dump({"domain": "domain.yaml", "interview_log": "interview/log.jsonl",
                                       "sources": sources}, sort_keys=False))
    ws = Workspace(where)
    if not ws.domain_path.exists():
        name = re.sub(r"[^a-z0-9_]+", "_", where.resolve().name.lower()).strip("_") or "domain"
        if not name[0].isalpha():
            name = "d_" + name
        ws.domain_path.write_text(f"domain: {name}\nversion: 1\n")
    return ws


def add_sources(ws, paths: list[str]):
    from ...workspace import Workspace
    cfg_path = ws.root / CONFIG
    cfg = yaml.safe_load(cfg_path.read_text()) or {}
    have = {s.get("path") for s in cfg.get("sources", [])}
    for i, p in enumerate(paths, 1):
        if not (ws.root / p).exists():
            raise ValueError(fixed(f"no {p} in {ws.root}", "give a path inside the domain's directory"))
        if p not in have:
            cfg.setdefault("sources", []).insert(0, {"id": re.sub(r"[^A-Za-z0-9_-]", "-", Path(p).stem) or f"s{i}",
                                                     "kind": "records", "path": p})
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return Workspace(ws.root)


# -- reading an open answer --------------------------------------------------------------------
def _parts(text: str) -> list[str]:
    return [p.strip() for p in text.split(";") if p.strip()]


def _pair(part: str) -> tuple[str, str]:
    if ":" not in part:
        raise ValueError(fixed(f"{part!r} has no `:`", "write `name: what it is`"))
    a, b = part.split(":", 1)
    return a.strip(), b.strip()


def ident(words: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", words.lower()).strip("_")


def camel(words: str) -> str:
    if re.fullmatch(r"[A-Z][A-Za-z0-9]*", words.strip()):
        return words.strip()
    return "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", words))


def thing(d: Any, words: str) -> str:
    from ...decl.words import normal
    w = words.strip()
    for name in d.objects:
        if normal(name) == normal(w) or name == w:
            return name
    for t in d.glossary:
        if normal(t) == normal(w) and camel(t) in d.objects:
            return camel(t)
    raise ValueError(fixed(f"{w!r} is not a thing in the draft", f"name one of {', '.join(d.objects) or '(none yet)'}"))


def value_of(d: Any, obj: str, fact: str, raw: str) -> Any:
    spec = d.objects[obj].properties.get(fact) if obj in d.objects else None
    t = getattr(spec, "type", None)
    try:
        if t == "integer":
            return int(raw)
        if t == "number":
            return float(raw) if "." in raw else int(raw)
    except ValueError:
        raise ValueError(fixed(f"{obj}.{fact} is a number, not {raw!r}", "give it as digits")) from None
    if t == "boolean":
        return raw.lower() in ("yes", "true", "y")
    return raw


def facts_of(d: Any, obj: str, text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in [x.strip() for x in text.split(",") if x.strip()]:
        k, _, v = f.replace("=", " ", 1).partition(" ")
        if not v:
            raise ValueError(fixed(f"{f!r} has no value", "write `fact value`, such as `days 12`"))
        key = ident(k)
        out[key] = value_of(d, obj, key, v.strip())
    return out


def prop_type(text: str) -> dict[str, Any]:
    t = text.strip().lower()
    if t in TYPES:
        return dict(TYPES[t])
    if "/" in t:
        return {"enum": [x.strip() for x in t.split("/") if x.strip()]}
    raise ValueError(fixed(f"{text!r} is not a type", "use number, integer, text, yes/no, date, or choices like `low/high`"))


def parse_open(ws, q, line: str) -> list[dict[str, Any]]:
    """The decisions an open answer makes, from the short forms the hints show."""
    from ...decl import Domain
    d = Domain.model_validate(ws.draft())
    kind, subject = q.kind, q.subject
    if kind == "cast" and subject == "roles":
        roles, decs = [], []
        for part in _parts(line):
            name, what = _pair(part) if ":" in part else (part, "")
            r = ident(name)
            roles.append(r)
            if what:
                decs.append({"path": f"glossary.{r}", "value": what})
        return [{"path": "roles", "value": roles}] + decs
    if kind == "cast" and subject == "objects":
        decs = []
        for part in _parts(line):
            head, _, facts = part.partition("|")
            name, what = _pair(head)
            props = {}
            for f in [x.strip() for x in facts.split(",") if x.strip()]:
                k, t = _pair(f)
                props[ident(k)] = prop_type(t)
            obj = camel(name)
            decs.append({"path": f"objects.{obj}", "value": {"description": what, "properties": props}})
            if obj != name.strip():
                decs.append({"path": f"glossary.{name.strip().lower()}", "value": what})
        return decs
    if kind == "cast" and (subject == "links" or subject.startswith("relate:")):
        decs = []
        for part in _parts(line):
            m = re.fullmatch(r"(.+?)\s*->\s*(.+?)\s+(one-to-one|one-to-many|many-to-one|many-to-many)(\s+required)?", part)
            if not m:
                raise ValueError(fixed(f"{part!r} is not a link", "write `Thing -> Other many-to-one`"))
            a, b = thing(d, m.group(1)), thing(d, m.group(2))
            decs.append({"path": f"links.{ident(b)}", "value": {"from": a, "to": b, "cardinality": m.group(3),
                                                                 "required": bool(m.group(4))}})
        return decs
    if kind == "cast" and subject.startswith("describe:"):
        return [{"path": f"objects.{subject.split(':', 1)[1]}.description", "value": line}]
    if kind == "example":
        ident_, _, facts = line.partition(":")
        return [{"path": "world.fixtures", "value": {subject: {"id": ident_.strip(), **facts_of(d, subject, facts)}}}]
    if kind == "actions":
        decs = []
        for part in _parts(line):
            name, rest = _pair(part)
            if "->" not in rest:
                raise ValueError(fixed(f"{part!r} names no thing", "end it with `-> Thing`, or `-> new Thing` when it makes one"))
            what, _, on = rest.rpartition("->")
            on = on.strip()
            creates = on.lower().startswith("new ")
            obj = thing(d, on[4:] if creates else on)
            value: dict[str, Any] = {"description": what.strip(), ("creates" if creates else "target"): obj}
            if creates:            # whoever makes the thing gives its facts
                value["params"] = {k: {x: y for x, y in p.model_dump(exclude_defaults=True).items()
                                       if x in ("type", "enum", "optional")}
                                   for k, p in d.objects[obj].properties.items()}
            decs.append({"path": f"actions.{ident(name)}", "value": value})
        return decs
    if kind == "transitions":
        obj = subject.split(":", 1)[1]
        parts = _parts(line)
        field_, states = _pair(parts[0])
        names = [s.strip() for s in states.split(",") if s.strip()]
        start = next((p.split(None, 1)[1].strip() for p in parts[1:] if p.lower().startswith("starts ")), names[0])
        acts = [n for n, a in d.actions.items() if a.target == obj and a.creates is None]
        f = ident(field_)
        return [{"path": f"objects.{obj}.properties.{f}", "value": {"enum": names}},
                {"path": f"transitions.{obj}", "value": {"field": f, "initial": start,
                                                         "matrix": {s: {a: "undecided" for a in acts} for s in names}}}]
    if kind == "invariants":
        check, _, why = line.partition("|")
        if not why.strip():
            raise ValueError(fixed("an invariant needs its reason", "write `check | why`, such as `target.days > 0 | A request is for at least a day.`"))
        n = len(d.invariants) + 1
        return [{"path": f"invariants.rule-{n}", "value": {"on": subject, "check": check.strip(), "reason": why.strip()}}]
    if kind == "world" and subject == "fixtures":
        decs = []
        for part in _parts(line):
            head, _, facts = part.partition(":")
            on, _, oid = head.strip().rpartition(" ")
            obj = thing(d, on)
            decs.append({"path": "world.fixtures", "value": {obj: {"id": oid, **facts_of(d, obj, facts)}}})
        return decs
    if kind == "world" and subject == "actors":
        out = {}
        for part in _parts(line):
            r, names = _pair(part)
            out[ident(r)] = [n.strip() for n in names.split(",") if n.strip()]
        return [{"path": "world.actors", "value": out}]
    if kind == "world" and subject == "scenarios":
        steps, first = [], None
        for part in _parts(line):
            m = re.fullmatch(r"(\S+)\s+(\S+)\s+(\S+)((?:\s+\S+=\S+)*)\s*->\s*(\S+)(?:\s+(\S+))?", part)
            if not m:
                raise ValueError(fixed(f"{part!r} is not a step", "write `role action ID -> stage`, or `-> refused`"))
            role, action, oid, params, result, code = m.groups()
            a = d.actions.get(action)
            if a is None:
                raise ValueError(fixed(f"no action {action!r}", f"use one of {', '.join(d.actions)}"))
            obj = a.creates or a.target
            ps = {k: value_of(d, obj, k, v) for k, v in (x.split("=", 1) for x in params.split())}
            first = first or oid
            expect: dict[str, Any] = {}
            if result == "refused":
                expect = {"denied_by": code or "matrix"}
            elif obj in d.transitions:
                expect = {"state": {f"{oid}.{d.transitions[obj].field}": result}}
            steps.append({"actor": {"role": ident(role)}, "do": action, "target": oid, "params": ps, "expect": expect})
        known = any((next(iter(f.values())) or {}).get("id") == first for f in d.world.fixtures if isinstance(f, dict) and f)
        return [{"path": f"scenarios.flow-{len(d.scenarios) + 1}",
                 "value": {"given": {"from_world": first} if known else {}, "steps": steps}}]
    if kind == "review" and subject == "glossary":
        return [{"path": f"glossary.{k.strip().lower()}", "value": v} for k, v in (_pair(p) for p in _parts(line))]
    raise ValueError(fixed("this question takes a numbered choice here",
                           "type the number of a choice; for anything else, ask your agent to draft it (Authoring)"))


def column(q, line: str) -> list[dict[str, Any]]:
    """`from submitted to approved`: the whole column, one move and refused in its other open stages."""
    m = re.fullmatch(r"(?:from\s+)?(\S+)\s*(?:->|to)\s*(\S+)", line.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(fixed(f"{line!r} is not a move", "type a choice's number, or `from STAGE to STAGE`"))
    frm, to = m.groups()
    cells = {p.split(".")[3]: p for p in q.decides}
    obj = q.decides[0].split(".")[1]
    if frm not in cells:
        raise ValueError(fixed(f"{frm!r} is not an open stage here", f"use one of {', '.join(cells)}"))
    return [{"path": p, "value": to if s == frm else {"deny": f"Not while {'an' if obj[:1].lower() in 'aeiou' else 'a'} "
                                                      f"{obj} is {s}."}} for s, p in cells.items()]


# -- the session -------------------------------------------------------------------------------
class Session:
    def __init__(self, where: Path, read: Callable[[str], str], out=None, scripted: bool = False):
        self.ws = open_workspace(where)
        self.read, self.out, self.scripted = read, out, scripted
        self.last_map: str | None = None

    def say(self, text: str = "") -> None:
        print(text, file=self.out or sys.stdout)

    def ask(self, prompt: str) -> str:
        line = self.read(prompt)
        if self.scripted:
            self.say(f"{prompt}{line}")
        return line

    def run(self) -> int:
        from ...workspace import AuthoringError
        last: tuple[str, int] | None = None
        while True:
            st, qs = self.ws.current_bundle()
            if st is None:
                bad = self.ws.questions(limit=1)
                if bad.get("stop", {}).get("why", "").startswith("the draft does not parse"):
                    raise SystemExit(fixed(bad["stop"]["why"], "fix domain.yaml at that place (docs/domain-schema.md), "
                                           "or restore it from git"))
                self.say("Every stage is done, and nothing is left to confirm. Next: `toprope-try` (if `toprope-init` "
                         "made this directory) or commit it (docs/interview.md).")
                return 0
            if not qs:
                self.say(f"[{st.title}] nothing to ask, yet the stage is not done; ask your agent (Authoring).")
                return 1
            q = qs[0]
            lines = self.ws._lines(self.ws.log_path)
            if last == (q.id, lines):
                self.say("  " + fixed("that answer left the question open", "answer it differently, or ask your agent "
                                      "to draft it (Authoring)"))
            m = self.ws.live_map()["text"]
            if m and m != self.last_map:
                self.say("\n" + m)
                self.last_map = m
            if st.name != "purpose":
                self.say(f"\n[{st.title}] {q.text}")
            try:
                if st.name == "purpose":
                    self.purpose(qs)
                elif q.kind == "confirm":
                    if not self.confirm(q):
                        return 0
                else:
                    self.one(q)
            except Stop:
                self.ws.note_attempt("abandoned", q)
                self.say("\nStopped: the answers ran out. What you answered is kept, proposed; run again to go on.")
                return 0
            except (AuthoringError, ValueError) as e:
                # a refused answer never ends the session: say why, and ask again (#242's review)
                self.ws.note_attempt("refused-answer", q, str(e))
                self.say(f"  {e}")
                self.say("  (asked again)")
                continue
            last = (q.id, self.ws._lines(self.ws.log_path))

    def one(self, q) -> None:
        recommended = next((i for i, c in enumerate(q.choices, 1) if c.recommended), None)
        for i, c in enumerate(q.choices, 1):
            self.say(f"  {i}. {c.label}" + ("   <- recommended" if c.recommended else ""))
            if c.recommended and c.why:
                self.say(f"       why: {c.why}")
        hint = HINTS.get(f"{q.kind}:{q.subject}") or HINTS.get(q.kind)
        if hint and q.kind not in ("row", "rest", "actor", "guard", "rule"):
            self.say(f"  ({hint})")
        prompt = (f"  choice [Enter = {recommended}]: " if recommended else
                  "  choice: " if q.choices and not hint else "  > ")
        line = self.ask(prompt).strip()
        if not line and recommended:
            c = q.choices[recommended - 1]
            self.ws.answer(q.id, f"Yes: {c.label}", f"choice:{c.id}")
            return
        if not line and q.choices and not hint:
            raise ValueError(fixed("nothing is recommended here", f"type a number from 1 to {len(q.choices)}"
                                   + (", or `from STAGE to STAGE`" if q.kind == "default" else "")))
        if line.isdigit() and q.choices:
            k = int(line)
            if not 1 <= k <= len(q.choices):
                raise ValueError(fixed(f"there is no choice {k}", f"type a number from 1 to {len(q.choices)}"))
            c = q.choices[k - 1]
            self.ws.answer(q.id, f"{k}: {c.label}", f"choice:{c.id}")
            return
        if q.kind == "sources":
            paths = [] if line.lower() in NONE | {""} else [p.strip() for p in line.split(",") if p.strip()]
            if paths:
                self.ws = add_sources(self.ws, paths)
            self.ws.answer(q.id, line or "No sources.", [])
            return
        if not line:
            raise ValueError(fixed("no answer", "type an answer, or a choice's number"))
        skip = next((c for c in q.choices if c.skip), None)
        if line.lower() in NONE and skip is not None:          # "nothing here": the stage's skip
            self.ws.answer(q.id, line, f"choice:{skip.id}")
            return
        if line.lower() in NONE and q.kind not in ("actor", "default", "row"):
            self.ws.answer(q.id, line, [])
            return
        if q.kind == "limit":
            self.ws.answer(q.id, line, self.ws.limit_answer(q, line))
            return
        if q.kind == "default":
            self.ws.answer(q.id, line, column(q, line))
            return
        self.ws.answer(q.id, line, parse_open(self.ws, q, line))

    def purpose(self, qs) -> None:
        """Purpose's parts in one answer: the declaration needs the problem before the rest."""
        doc = self.ws.draft()
        purpose = dict(doc.get("purpose") or {})
        said = []
        for key in ("problem", "metric", "announcement"):
            q = next((x for x in qs if x.subject == key), None)
            if q is None:
                continue
            self.say(f"\n[Purpose] {q.text}")
            self.say(f"  ({HINTS['purpose:' + key]})")
            line = self.ask("  > ").strip()
            if not line:
                raise ValueError(fixed("no answer", "type an answer in a few words"))
            said.append(line)
            if key == "metric":
                name, _, direction = line.rpartition(",")
                if direction.strip().lower() not in ("up", "down"):
                    raise ValueError(fixed(f"{line!r} does not say up or down", "end it with `, up` or `, down`"))
                purpose["success_metric"] = {"name": name.strip(), "direction": direction.strip().lower()}
            else:
                purpose[key] = line
        st, all_qs = self.ws.current_bundle()
        bundle = self.ws._bundle_id(st.name, all_qs)
        self.ws.answer(bundle, " / ".join(said), [{"path": "purpose", "value": purpose}])

    def confirm(self, q) -> bool:
        self.say(self.ws.render_review())
        line = self.ask("  Confirm all of it? Type yes to confirm (anything else: not now): ").strip().lower()
        if line != "yes":
            self.say("Nothing confirmed. Run again to confirm, or confirm one element at a time with your agent.")
            return False
        out = self.ws.confirm(q.decides, via="terminal")
        self.say(f"Confirmed {len(out['confirmed'])} element(s), as {self.ws.identity() or 'you'}.")
        return True


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    where = Path(args.dir)
    if args.share:
        from ...workspace import interview_share
        ws = open_workspace(where)
        print(json.dumps(interview_share(ws._read(ws.log_path)), indent=2, ensure_ascii=False))
        return
    if args.answers:
        p = Path(args.answers)
        if not p.is_file():
            raise SystemExit(fixed(f"no answers file {p}", "give a file with one answer per line"))
        lines = iter(x for x in p.read_text().splitlines() if not x.lstrip().startswith("#"))
        scripted = True
    elif not sys.stdin.isatty():
        lines = iter(x.rstrip("\n") for x in sys.stdin if not x.lstrip().startswith("#"))
        scripted = True
    else:
        lines, scripted = None, False

    def read(prompt: str) -> str:
        if lines is None:
            try:
                return input(prompt)
            except EOFError:
                raise Stop() from None
        try:
            return next(lines)
        except StopIteration:
            raise Stop() from None

    raise SystemExit(Session(where, read, scripted=scripted).run())


__all__ = ["build_parser", "main", "open_workspace", "parse_open"]

if __name__ == "__main__":
    main()
