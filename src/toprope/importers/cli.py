"""`toprope-import`: a proposed draft from a source a team already has (ADR-0049 A1, ADR-0051).

    toprope-import openapi api.yaml --domain shop --out drafts/shop.domain.yaml
    toprope-import sql schema.sql --domain shop --profile our-conventions.yaml
    toprope-import workflow https://jira.example.com/export.json --via http --domain support
    toprope-import --list                    # the readers and extractors installed

The kind names an extractor (a format), `--via` a reader (where the source lives); both are
ports that installed packages extend. `--profile` holds a team's conventions: which fields are
stages, where roles come from, what to ignore or rename. Every element written is `proposed`,
citing its place; then the command prints what the source cannot say. A person confirms what is
right (ADR-0041).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from ..errors import fixed
from . import Profile, import_source, kinds


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-import", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", nargs="?", help="the source's format: an extractor (see --list)")
    ap.add_argument("source", nargs="?", help="where the source is, as the reader takes it (a path, a URL)")
    ap.add_argument("--via", default="file", help="the reader that reaches the source (default: file)")
    ap.add_argument("--profile", help="a YAML file of the team's conventions")
    ap.add_argument("--domain", default="imported", help="the new domain's name")
    ap.add_argument("--out", help="where to write the draft (default: <domain>.domain.yaml here)")
    ap.add_argument("--list", action="store_true", help="the readers and extractors installed")
    return ap


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    if a.list or not (a.kind and a.source):
        k = kinds()
        print(f"readers: {', '.join(k['readers'])}\nextractors: {', '.join(k['extractors'])}")
        if not a.list:
            raise SystemExit(fixed("no source given", "give `toprope-import <extractor> <source>`"))
        return
    try:
        out = import_source(a.kind, a.source, domain=a.domain, profile=Profile.load(a.profile), via=a.via)
    except (yaml.YAMLError, ValueError, UnicodeDecodeError) as e:
        raise SystemExit(fixed(f"{a.source} does not read as {a.kind}: {e}",
                               "give the export as it was written, or another extractor")) from None
    draft = out["draft"]
    if not draft["objects"] and not draft["actions"]:
        raise SystemExit(fixed(f"nothing to import from {a.source}",
                               f"check that it is {a.kind}: no things, enums or statuses were found"))
    dest = Path(a.out) if a.out else Path(f"{draft['domain']}.domain.yaml")
    if dest.exists():
        raise SystemExit(fixed(f"{dest} exists", "give --out a new file; to add to a draft, propose the elements there"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(draft, sort_keys=False, allow_unicode=True))
    print(f"wrote {dest}: {len(draft['objects'])} thing(s), {len(draft['actions'])} action(s), "
          f"{len(draft['transitions'])} with stages; every element is proposed, citing {a.source}")
    for title, items in (("conflicts in the source", out["conflicts"]), ("what the source cannot say", out["questions"])):
        if items:
            print(f"\n{title}:")
            for q in items:
                print(f"  - {q}")


__all__ = ["build_parser", "main"]
