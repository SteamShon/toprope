"""Start a domain from a template and see its rules work (ADR-0049, A3 and A4; ADR-0053, F2).

    toprope-init --list
    toprope-init my-approvals --template approval        # writes ./my-approvals/
    toprope-init "Staff submit requests; a manager approves them. Nobody approves their own."
    cd my-approvals && toprope-try                       # the template's story, step by step
    toprope-try --check                                  # after editing domain.yaml: what changed
    toprope-try --accept                                 # the story's expectations become today's outcomes
    toprope-try --reset                                  # the domain's store starts again from the examples
    toprope-set --list                                   # the template's settings and their values
    toprope-set window_days=30                           # change a rule without editing YAML
    toprope-rule --help                                  # add your own rule, also without YAML

`toprope-init` writes a working domain: `domain.yaml` (the template's declaration, renamed),
`tokens.yaml` (the people and the agent of its story), `story.yaml`, and a `toprope.yaml` so
that `toprope-run <action> <target> --token t-…` needs no other option. No YAML is written by
hand to get there. Given a sentence instead of a name, it picks the closest template by its
words and turns the rules it recognises into `toprope-rule` commands, marked `proposed` until
you confirm them (`toprope-rule confirm`); what it did not understand it asks as questions.

`toprope-try` plays the story on a fresh in-memory store seeded with the declaration's examples
(the domain's own store is not touched) and prints who asked what, and what the gate said,
with the reason for each refusal. It exits 1 if a step does not end as the story says, so a
story is also a test. `--check` compares `domain.yaml` with the template it came from and
prints the change check's impact report: what an edit touches, before anything ships.

The domain's own store (`.toprope/events.db`, which `toprope-run` uses) is seeded with the
examples once. When a command changes the examples and nothing was done in the store yet, it
starts the store again by itself; otherwise `toprope-try --reset` does it and keeps the old file.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from ...errors import fixed

TEMPLATES = "toprope.templates"
NAME = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
PROSE_WORDS = 4                                     # a first argument of this many words is a sentence, not a name


def templates() -> dict[str, dict[str, Any]]:
    out = {}
    root = resources.files(TEMPLATES)
    for d in sorted(root.iterdir(), key=lambda x: x.name):
        if d.is_dir() and (d / "story.yaml").is_file():
            out[d.name] = yaml.safe_load((d / "story.yaml").read_text())
    return out


def _template_dir(name: str):
    root = resources.files(TEMPLATES)
    d = root / name
    if not (d.is_dir() and (d / "domain.yaml").is_file()):
        raise SystemExit(fixed(f"no template {name!r}", f"use one of {', '.join(templates())} "
                               "(`toprope-init --list` describes them)"))
    return d


def init(name: str, template: str, where: Path) -> Path:
    if not NAME.match(name):
        raise SystemExit(fixed(f"{name!r} is not a domain name",
                               "use lowercase letters, digits and dashes, starting with a letter"))
    src = _template_dir(template)
    out = where / name
    if out.exists():
        raise SystemExit(fixed(f"{out} exists", "choose another name, or remove that directory"))
    out.mkdir(parents=True)
    try:
        _write(out, src, name, template)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)          # nothing half-written is left to block a retry
        raise
    return out


def _write(out: Path, src: Any, name: str, template: str) -> None:
    for f in ("domain.yaml", "tokens.yaml", "story.yaml"):
        (out / f).write_text((src / f).read_text())
    decl = (out / "domain.yaml").read_text()
    decl = re.sub(r"^domain: .*$", f"domain: {name}", decl, count=1, flags=re.M)
    (out / "domain.yaml").write_text(decl)
    (out / ".template").write_text((src / "domain.yaml").read_text())   # what --check compares with
    (out / "toprope.yaml").write_text(
        f"# toprope-run options for this domain (from template {template}).\n"
        "domain: domain.yaml\n"
        "store: sqlite:.toprope/events.db\n"
        "identity: static:tokens.yaml\n"
        "failures: .toprope/failures\n")
    from ...decl import load_domain
    (out / ".toprope").mkdir()
    _seed(out / ".toprope" / "events.db", load_domain(out / "domain.yaml"))   # the examples, once


def _seed(f: Path, d: Any) -> None:
    from ...exec import Execution
    from ...identity import StaticIdentity
    from ...store import open_store
    store = open_store(f"sqlite:{f}")
    try:
        Execution(d, store, StaticIdentity({})).seed_world()
    finally:
        store.close()                                      # type: ignore[attr-defined]


# -- the domain's own store, kept in step with its declaration (ADR-0053, F2) -----------------

def store_file(where: Path) -> Path | None:
    """The SQLite file `toprope.yaml` names as the store, or None if it names another kind."""
    cfg = where / "toprope.yaml"
    if not cfg.is_file():
        return None
    spec = (yaml.safe_load(cfg.read_text()) or {}).get("store")
    if not isinstance(spec, str) or not spec.startswith("sqlite:") or spec == "sqlite::memory:":
        return None
    p = Path(spec[len("sqlite:"):])
    return p if p.is_absolute() else where / p


def _norm(v: Any) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def store_drift(store: Any, d: Any) -> tuple[list[str], int]:
    """How the examples in a store differ from the declaration's, and how many things were done
    in the store since it was seeded (actions taken and refusals recorded)."""
    want = {data["id"]: (obj, data) for fx in d.world.fixtures for obj, data in fx.items()}
    drift, done, seen = [], 0, set()
    for s in store.streams():
        events = store.read(s)
        done += len(store.read_attempts(s))
        if not events or not (events[0].payload or {}).get("fixture"):
            done += len(events)
            continue
        done += len(events) - 1
        seen.add(s)
        w = want.get(s)
        if w is None:
            drift.append(f"{s} is no longer an example")
        elif w[0] != events[0].aggregate or _norm(w[1]) != _norm(events[0].payload.get("changes")):
            drift.append(f"{s} changed")
    drift += [f"{i} is a new example" for i in want if i not in seen]
    return drift, done


def _drift_of(f: Path, d: Any) -> tuple[list[str], int]:
    from ...store import open_store
    store = open_store(f"sqlite:{f}")
    try:
        return store_drift(store, d)
    finally:
        store.close()                                      # type: ignore[attr-defined]


def _set_aside(f: Path, keep: bool) -> Path | None:
    kept = f.with_name(f"{f.stem}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}{f.suffix}") if keep else None
    for sib in (f, f.with_name(f.name + "-wal"), f.with_name(f.name + "-shm")):
        if sib.exists():
            if kept is not None:
                sib.rename(kept.with_name(kept.name + sib.name[len(f.name):]))
            else:
                sib.unlink()
    return kept


def reset_store(where: Path, d: Any = None) -> str:
    """Start the domain's store again from the declaration's examples. The old file is kept."""
    f = store_file(where)
    if f is None:
        raise SystemExit(fixed(f"{where / 'toprope.yaml'} names no SQLite store to reset",
                               "run --reset in a directory toprope-init wrote"))
    d = d if d is not None else load(where / "domain.yaml")
    kept = _set_aside(f, keep=True) if f.exists() else None
    f.parent.mkdir(parents=True, exist_ok=True)
    _seed(f, d)
    rel = f.relative_to(where) if f.is_relative_to(where) else f
    return (f"{rel} now holds the examples of domain.yaml" +
            (f"; what was there before is kept in {kept.name}" if kept else ""))


def sync_store(where: Path, d: Any) -> str | None:
    """After a command changed the declaration: if the store's examples are no longer the
    declaration's, start it again when nothing was done in it, or say how to (never silently
    drop what someone did)."""
    f = store_file(where)
    if f is None or not f.exists():
        return None
    drift, done = _drift_of(f, d)
    if not drift:
        return None
    if done == 0:
        _set_aside(f, keep=False)
        _seed(f, d)
        return "the domain's store now holds the new examples (nothing had been done in it yet)"
    return (f"the domain's store was seeded before this change ({'; '.join(drift[:3])}) and holds {done} "
            f"thing(s) done since; to start it again from the new examples: {hint('toprope-try --reset')} "
            "(the old file is kept)")


def hint(command: str) -> str:
    """A command as the person can type it: from a clone (no install), through `uv run`."""
    root = Path(__file__).resolve().parents[4]
    if (root / "pyproject.toml").is_file() and (root / "src" / "toprope").is_dir():
        return f"uv run --project {root} {command}"
    return command


# -- YAML written back by commands -------------------------------------------------------------

class _Dumper(yaml.SafeDumper):
    """Short mappings and lists of scalars stay on one line, as the templates write them."""


def _short(v: Any) -> bool:
    return not isinstance(v, (dict, list)) or (isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v))


def _repr_dict(dumper: Any, data: dict) -> Any:
    flow = bool(data) and all(_short(v) for v in data.values()) and len(_norm(data)) < 100
    return dumper.represent_mapping("tag:yaml.org,2002:map", data, flow_style=flow)


def _repr_list(dumper: Any, data: list) -> Any:
    flow = all(not isinstance(x, (dict, list)) for x in data) and len(_norm(data)) < 80
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_Dumper.add_representer(dict, _repr_dict)
_Dumper.add_representer(list, _repr_list)
# Quote what a YAML 1.2 reader would not read back as text (`1e3`), as well as YAML 1.1's words.
_Dumper.add_implicit_resolver(
    "tag:yaml.org,2002:float", re.compile(r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?)$"),
    list("-+0123456789."))


def dump_yaml(doc: Any, name: str, reread: Any = None) -> str:
    """`doc` as YAML that reads back to the same thing, or an error that says so."""
    from ...decl import load_yaml
    text = yaml.dump(doc, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110)
    if (reread or load_yaml)(text) != doc:
        raise SystemExit(fixed(f"{name} would not read back as written",
                               "a value holds characters YAML reads as something else; give it in plain words"))
    return text


def load(domain_file: Path):
    """The declaration, or an error that says where it is wrong and what to do (D1)."""
    from pydantic import ValidationError

    from ...decl import load_domain, validate_domain
    try:
        d = load_domain(domain_file)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first["loc"])
        hint = " (a check is text: quote it, e.g. `check: \"true\"`)" if first.get("type") == "string_type" else ""
        raise SystemExit(fixed(f"{domain_file.name}: {where}: {first['msg']}{hint}",
                               "fix that line; docs/domain-schema.md describes every field")) from None
    except Exception as e:                              # noqa: BLE001 - not YAML at all
        raise SystemExit(fixed(f"{domain_file.name} cannot be read: {e}", "fix the YAML at the line named")) from None
    errors = [i for i in validate_domain(d) if i.severity == "error"]
    if errors:
        raise SystemExit(fixed(f"{domain_file.name}: " + "; ".join(f"{i.code} at {i.where}: {i.message}"
                                                                   for i in errors[:3]),
                               "fix those elements; docs/domain-schema.md describes them"))
    return d


def _execution(domain_file: Path, tokens: Path):
    from ...adapters.mcp.cli import open_identity
    from ...exec import Execution
    from ...store import open_store
    d = load(domain_file)
    ex = Execution(d, open_store("memory"), open_identity(f"static:{tokens}"))
    ex.seed_world()
    return d, ex


def play(where: Path) -> tuple[bool, list[dict[str, Any]]]:
    story_file, domain_file, tokens = where / "story.yaml", where / "domain.yaml", where / "tokens.yaml"
    for f in (story_file, domain_file, tokens):
        if not f.is_file():
            raise SystemExit(fixed(f"no {f.name} in {where}",
                                   "run toprope-try in a directory toprope-init wrote, or give --dir"))
    story = yaml.safe_load(story_file.read_text())
    d, ex = _execution(domain_file, tokens)
    rows, ok = [], True
    for st in story.get("steps", []):
        if st.get("expect") == "denied" and not st.get("code"):
            raise SystemExit(fixed(f"a step of story.yaml expects a refusal without saying which ({st['action']} "
                                   f"{st['target']})", "give the step the `code` of the refusal it expects, so "
                                   "any other refusal (a wrong token, a missing grant) does not pass for it"))
        if st["action"] not in d.actions:
            raise SystemExit(fixed(f"the story names {st['action']!r}, which domain.yaml does not declare",
                                   "rename the step's action in story.yaml, or put the action back"))
        o = ex.submit(st["who"], st["action"], st["target"], dict(st.get("params") or {}),
                      idempotency_key=str(uuid.uuid4()))
        status = "ok" if o.ok else "denied"
        as_told = status == st.get("expect", status) and (not st.get("code") or st["code"] == o.code)
        ok = ok and as_told
        rows.append({"who": st.get("as", st["who"]), "asks": st.get("says", f"{st['action']} {st['target']}"),
                     "result": status, "code": o.code, "reason": o.reason, "as_told": as_told,
                     "expected": st.get("expect"), "expected_code": st.get("code")})
    return ok, rows


def render(story: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [f"{story.get('title', 'The story')}", "", " ".join(str(story.get("about", "")).split()), ""]
    width = max([len(r["who"]) for r in rows] + [3])
    for r in rows:
        mark = "" if r["as_told"] else f"    <- the story expected {r['expected']}" + (
            f" ({r['expected_code']})" if r["expected_code"] else "")
        said = f"{r['result']}: {r['reason']}" if r["result"] == "denied" else "done"
        lines.append(f"{r['who']:<{width}}  asks to {r['asks']}")
        lines.append(f"{'':<{width}}  -> {said}{mark}")
    if story.get("next"):
        lines += ["", "Next: " + " ".join(str(story["next"]).split())]
    return "\n".join(lines) + "\n"


def settings_of(where: Path) -> dict[str, dict[str, Any]]:
    story = yaml.safe_load((where / "story.yaml").read_text()) or {}
    return story.get("settings") or {}


ROLE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,40}")


def _pattern(template_text: str) -> re.Pattern:
    """The template's text with `{value}` as the one thing that may vary."""
    head, _, tail = template_text.partition("{value}")
    return re.compile(re.escape(head) + r"(.+?)" + re.escape(tail) + r"\Z")


def _find(raw: dict[str, Any], spec: dict[str, Any], name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    segs = spec["at"].split(".")                       # actions.<action>.preconditions.<id>
    action = (raw.get("actions") or {}).get(segs[1])
    pre = next((p for p in (action or {}).get("preconditions") or [] if p.get("id") == segs[3]), None)
    if action is None or pre is None:
        raise SystemExit(fixed(f"{name} names {spec['at']}, which domain.yaml no longer has",
                               "put that precondition back, or edit domain.yaml by hand"))
    return action, pre


def current_values(where: Path) -> dict[str, str]:
    """Each setting's value, read from the rule in domain.yaml itself, so a hand edit shows."""
    from ...decl import load_yaml
    raw = load_yaml((where / "domain.yaml").read_text())
    out = {}
    for name, spec in settings_of(where).items():
        try:
            _, pre = _find(raw, spec, name)
        except SystemExit:
            out[name] = "(its rule is gone)"
            continue
        m = _pattern(spec["check"]).match(str(pre.get("check", "")))
        out[name] = m.group(1) if m else "(edited by hand)"
    return out


def _value(name: str, spec: dict[str, Any], raw: str, action: dict[str, Any]) -> Any:
    kind = spec.get("type", "string")
    if kind == "integer":
        try:
            v = int(raw)
        except ValueError:
            raise SystemExit(fixed(f"{name} is a whole number, not {raw!r}", f"give e.g. {name}={spec.get('default')}")) from None
        if v <= 0:
            raise SystemExit(fixed(f"{name} must be positive, not {v}", f"give e.g. {name}={spec.get('default')}"))
        return v
    if kind == "role":
        may = [r for r in action.get("actor") or [] if isinstance(r, str)]
        if not ROLE.fullmatch(raw):          # it goes inside quotes in a check (#215's review)
            raise SystemExit(fixed(f"{raw!r} is not a role name", "use letters, digits, `_` and `-`"))
        if raw not in may:
            raise SystemExit(fixed(f"{raw!r} may not take this action, so nobody could pass the rule",
                                   f"use one of {', '.join(may)}"))
        return raw
    if not re.fullmatch(r"[\w .:-]{1,80}", raw):
        raise SystemExit(fixed(f"{name}: {raw!r} has characters a setting may not hold", "use letters, digits and spaces"))
    return raw


def _replace_line(lines: list[str], start: int, key: str, value: str) -> None:
    """Set `key:` in the list item that starts at `start`, keeping its indentation and every
    other line of the file as it was (comments, quoting, layout)."""
    item = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start, len(lines)):
        body = lines[i].lstrip()
        if i > start and (body.startswith("- ") and len(lines[i]) - len(body) <= item
                          or body and len(lines[i]) - len(body) < item):
            break
        m = re.match(rf"^(\s*(?:- )?){re.escape(key)}:\s", lines[i])
        if m:
            lines[i] = f"{m.group(1)}{key}: {json.dumps(value, ensure_ascii=False)}"
            return
    raise SystemExit(fixed(f"no `{key}:` line found for the setting's rule",
                           "write the rule's check and reason on their own lines, as the template does"))


def apply_settings(where: Path, assignments: list[str]) -> list[str]:
    """Set the template's settings in domain.yaml: each names one precondition and fills in its
    check and reason. Only those two lines change; the rest of the file stays as it was. Returns
    what changed, in words. Nothing is written if any value is wrong."""
    from ...decl import load_yaml                       # YAML 1.1 would read the key `on:` as true
    specs = settings_of(where)
    decl_file = where / "domain.yaml"
    text = decl_file.read_text()
    raw = load_yaml(text)
    before = current_values(where)
    lines, said = text.split("\n"), []
    for a in assignments:
        name, eq, given = a.partition("=")
        if not eq or name not in specs:
            raise SystemExit(fixed(f"no setting {name!r}" if eq else f"{a!r} is not name=value",
                                   f"use one of {', '.join(specs) or '(this template has none)'}, as name=value"))
        spec = specs[name]
        action, pre = _find(raw, spec, name)
        value = _value(name, spec, given.strip(), action)
        check_text, reason = spec["check"].format(value=value), spec["reason"].format(value=value)
        at = next((i for i, ln in enumerate(lines) if re.match(rf"^\s*- id: {re.escape(pre['id'])}\s*$", ln)), None)
        if at is None:
            raise SystemExit(fixed(f"no `- id: {pre['id']}` line in domain.yaml",
                                   "write the precondition's id on its own line, as the template does"))
        _replace_line(lines, at, "check", check_text)
        _replace_line(lines, at, "reason", reason)
        pre["check"], pre["reason"] = check_text, reason
        said.append(f"{name}: {before.get(name)} -> {value} ({reason})")
    out = "\n".join(lines)
    if load_yaml(out) != raw:                           # the edit changed exactly what it meant to
        raise SystemExit(fixed("the edited domain.yaml would not read back as intended",
                               "edit the rule by hand; the file's layout is not one toprope-set can edit"))
    decl_file.write_text(out)
    return said


def check(where: Path) -> str:
    from ...check import change_check
    from ...decl import Domain, load_yaml
    base = where / ".template"
    if not base.is_file():
        raise SystemExit(fixed(f"no template recorded in {where}", "run --check in a directory toprope-init wrote"))
    new = load(where / "domain.yaml")
    raw = load_yaml(base.read_text())
    raw["domain"] = new.domain
    r = change_check(new, Domain.model_validate(raw), examples=20)
    out = [f"compared with the template: {r.impact['summary'] if r.impact else 'no change'}", r.summary()]
    for g in r.groups()[:10]:
        out.append(f"  {g['severity']}: {g['check']}: {g['problem']}" + (f" (x{g['count']})" if g["count"] > 1 else ""))
    return "\n".join(out) + "\n"


def init_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-init", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", help="the new domain's name, and its directory; or a sentence that "
                    "describes your workflow and its rules (then the name is --name, or taken from the template)")
    ap.add_argument("prose", nargs="?", help="a sentence that describes your workflow and its rules")
    ap.add_argument("--name", dest="as_name", help="the domain's name, when the first argument is a sentence")
    ap.add_argument("--template", help="the template to start from (see --list)")
    ap.add_argument("--dir", default=".", help="where to write the domain's directory (default: here)")
    ap.add_argument("--list", action="store_true", help="list the templates")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    help="a template setting (see `toprope-set --list` in the new directory)")
    return ap


def set_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-set", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("assignments", nargs="*", metavar="NAME=VALUE", help="settings to change")
    ap.add_argument("--dir", default=".", help="the domain's directory (default: here)")
    ap.add_argument("--list", action="store_true", help="the settings, what each means, and its value")
    return ap


def try_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-try", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="the domain's directory (default: here)")
    ap.add_argument("--check", action="store_true", help="compare domain.yaml with its template")
    ap.add_argument("--json", action="store_true", help="the steps as JSON")
    ap.add_argument("--accept", action="store_true",
                    help="make each step's expectation in story.yaml what happens now, and show what changed")
    ap.add_argument("--reset", action="store_true",
                    help="start the domain's store (the one toprope-run uses) again from domain.yaml's examples; "
                         "the old file is kept")
    ap.add_argument("--yes", action="store_true",
                    help="with --accept: also accept steps that showed a rule refusing and now pass")
    return ap


def init_main(argv: list[str] | None = None) -> None:
    a = init_parser().parse_args(argv)
    if a.name and len(a.name.split()) >= PROSE_WORDS and not a.prose:
        a.name, a.prose = a.as_name, a.name                  # `toprope-init "<a sentence>"`
    if a.prose:
        from .prose import start_from_prose
        start_from_prose(a.prose, a.name, Path(a.dir), template=a.template)
        return
    if a.list or not a.name:
        for name, story in templates().items():
            print(f"{name:<10} {story.get('title', '')}")
        if not a.list:
            print("\nthen: toprope-init <name> --template <template>")
        return
    if not a.template:
        raise SystemExit(fixed("no --template", f"choose one of {', '.join(templates())}"))
    out = init(a.name, a.template, Path(a.dir))
    if a.set:
        try:
            for line in apply_settings(out, a.set):
                print(line)
        except SystemExit:
            shutil.rmtree(out, ignore_errors=True)
            raise
    print(f"wrote {out}/: domain.yaml, tokens.yaml, story.yaml, toprope.yaml\n\n"
          f"next:\n  cd {out}\n  {hint('toprope-try')}")


def set_main(argv: list[str] | None = None) -> None:
    a = set_parser().parse_args(argv)
    where = Path(a.dir)
    if not (where / "story.yaml").is_file():
        raise SystemExit(fixed(f"no story.yaml in {where}", "run toprope-set in a directory toprope-init wrote"))
    specs, current = settings_of(where), current_values(where)
    if a.list or not a.assignments:
        if not specs:
            print("this template has no settings; edit domain.yaml, then `toprope-try --check`")
        for name, spec in specs.items():
            print(f"{name} = {current.get(name)}    {spec.get('says', '')}")
        return
    before = (where / "domain.yaml").read_text()
    try:
        for line in apply_settings(where, a.assignments):
            print(line)
        load(where / "domain.yaml")
    except SystemExit:
        (where / "domain.yaml").write_text(before)
        raise
    print(check(where), end="")
    report_story(where)
    if said := sync_store(where, load(where / "domain.yaml")):
        print(said)


def report_story(where: Path) -> None:
    """Which steps of the story now end differently, and how to record that as intended."""
    ok, rows = play(where)
    changed = [r for r in rows if not r["as_told"]]
    for r in changed:
        print(f"the story now ends differently: {r['who']} asks to {r['asks']} -> {r['result']}"
              + (f" ({r['reason']})" if r["reason"] else ""))
    if changed:
        print(f"if that is what you meant, record it in the story: {hint('toprope-try --accept')}")
    else:
        print("the story still ends as told")


CANNOT_RUN = ("not-found", "exists", "invalid-command", "unauthenticated", "unknown-action")


def accept(where: Path, yes: bool = False) -> list[str]:
    """Make each step's expectation what happens now (the person has seen the outcome and says it
    is intended). A step that cannot run at all is not accepted: it names its fix instead."""
    ok, rows = play(where)
    story = yaml.safe_load((where / "story.yaml").read_text())
    said, broken, undone = [], [], []
    for i, (st, r) in enumerate(zip(story.get("steps", []), rows), 1):
        if r["as_told"]:
            continue
        if r["code"] in CANNOT_RUN:
            broken.append(f"step {i} ({st['action']} {st['target']}): {r['reason']}")
            continue
        if st.get("rule") and st.get("expect") == "denied" and r["result"] == "ok" and not yes:
            undone.append(f"step {i} showed {st['rule']} refusing and now passes")
        was = f"{st.get('expect')}" + (f" ({st['code']})" if st.get("code") else "")
        st["expect"] = r["result"]
        if r["result"] == "denied":
            st["code"] = r["code"]
        else:
            st.pop("code", None)
        now = f"{st['expect']}" + (f" ({st['code']})" if st.get("code") else "")
        said.append(f"step {i}: {r['who']} asks to {r['asks']}: {was} -> {now}")
    if broken:
        raise SystemExit(fixed("these steps cannot run on domain.yaml as it is: " + "; ".join(broken),
                               "undo the hand edit that removed or renamed what the step names (`toprope-rename` "
                               "renames a thing everywhere, the story too); nothing was written"))
    if undone:
        raise SystemExit(fixed("; ".join(undone) + " (a rule may no longer hold)",
                               "if that is what you meant, run `toprope-try --accept --yes`; otherwise undo the "
                               "change; nothing was written"))
    if said:
        (where / "story.yaml").write_text(dump_yaml(story, "story.yaml", yaml.safe_load))
    return said


def try_main(argv: list[str] | None = None) -> None:
    a = try_parser().parse_args(argv)
    where = Path(a.dir)
    if a.check:
        print(check(where), end="")
        return
    if a.reset:
        print(reset_store(where))
        return
    if a.accept:
        said = accept(where, a.yes)
        for line in said:
            print(line)
        print("story.yaml now expects what happens today" if said else "the story already ends as told")
        return
    ok, rows = play(where)
    story = yaml.safe_load((where / "story.yaml").read_text())
    print(json.dumps(rows, indent=2) if a.json else render(story, rows), end="")
    if not ok:
        raise SystemExit(fixed("a step did not end as the story says", "if you changed domain.yaml on purpose, "
                               "run `toprope-try --accept` to make the story expect what happens now; "
                               "otherwise undo the change"))


__all__ = ["accept", "apply_settings", "check", "dump_yaml", "hint", "init", "reset_store", "store_drift", "store_file", "sync_store", "set_main", "set_parser", "settings_of", "init_main", "init_parser", "play", "templates", "try_main", "try_parser"]
