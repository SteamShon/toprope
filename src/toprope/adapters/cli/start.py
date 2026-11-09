"""Start a domain from a template and see its rules work (ADR-0049, A3 and A4).

    toprope-init --list
    toprope-init my-approvals --template approval        # writes ./my-approvals/
    cd my-approvals && toprope-try                       # the template's story, step by step
    toprope-try --check                                  # after editing domain.yaml: what changed

`toprope-init` writes a working domain: `domain.yaml` (the template's declaration, renamed),
`tokens.yaml` (the people and the agent of its story), `story.yaml`, and a `toprope.yaml` so
that `toprope-run <action> <target> --token t-…` needs no other option. No YAML is written by
hand to get there.

`toprope-try` plays the story on a fresh in-memory store seeded with the declaration's examples
(the domain's own store is not touched) and prints who asked what, and what the gate said,
with the reason for each refusal. It exits 1 if a step does not end as the story says, so a
story is also a test. `--check` compares `domain.yaml` with the template it came from and
prints the change check's impact report: what an edit touches, before anything ships.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from ...errors import fixed

TEMPLATES = "toprope.templates"
NAME = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


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
    from ...exec import Execution
    from ...identity import StaticIdentity
    from ...store import open_store
    (out / ".toprope").mkdir()
    ex = Execution(load_domain(out / "domain.yaml"), open_store(f"sqlite:{out / '.toprope' / 'events.db'}"),
                   StaticIdentity({}))
    ex.seed_world()                                        # the examples, once, into its own store
    return out


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
    ap.add_argument("name", nargs="?", help="the new domain's name, and its directory")
    ap.add_argument("--template", help="the template to start from (see --list)")
    ap.add_argument("--dir", default=".", help="where to write the domain's directory (default: here)")
    ap.add_argument("--list", action="store_true", help="list the templates")
    return ap


def try_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-try", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="the domain's directory (default: here)")
    ap.add_argument("--check", action="store_true", help="compare domain.yaml with its template")
    ap.add_argument("--json", action="store_true", help="the steps as JSON")
    return ap


def init_main(argv: list[str] | None = None) -> None:
    a = init_parser().parse_args(argv)
    if a.list or not a.name:
        for name, story in templates().items():
            print(f"{name:<10} {story.get('title', '')}")
        if not a.list:
            print("\nthen: toprope-init <name> --template <template>")
        return
    if not a.template:
        raise SystemExit(fixed("no --template", f"choose one of {', '.join(templates())}"))
    out = init(a.name, a.template, Path(a.dir))
    print(f"wrote {out}/: domain.yaml, tokens.yaml, story.yaml, toprope.yaml\n\n"
          f"next:\n  cd {out}\n  toprope-try")


def try_main(argv: list[str] | None = None) -> None:
    a = try_parser().parse_args(argv)
    where = Path(a.dir)
    if a.check:
        print(check(where), end="")
        return
    ok, rows = play(where)
    story = yaml.safe_load((where / "story.yaml").read_text())
    print(json.dumps(rows, indent=2) if a.json else render(story, rows), end="")
    if not ok:
        raise SystemExit(fixed("a step did not end as the story says", "if you changed domain.yaml on purpose, "
                               "update the step's `expect` in story.yaml; otherwise undo the change"))


__all__ = ["check", "init", "init_main", "init_parser", "play", "templates", "try_main", "try_parser"]
