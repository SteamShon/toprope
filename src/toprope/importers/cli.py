"""`toprope-import`: a proposed draft from a source a team already has (ADR-0049 A1, ADR-0051).

    toprope-import openapi api.yaml --domain shop --out drafts/shop.domain.yaml
    toprope-import sql schema.sql --into drafts/shop.domain.yaml     # join a second source to the draft
    toprope-import sql schema.sql --domain shop --profile our-conventions.yaml
    toprope-import workflow https://jira.example.com/export.json --via http --domain support
    toprope-import rules AGENTS.md --questions q.yaml   # candidate rules and contradictions
    toprope-import rules .claude/skills --via tree      # every Markdown file under a folder
    toprope-import mcp "python server.py" --domain payments --binding-out payments.binding.yaml
    toprope-import --list                    # the readers and extractors installed

Into the change loop (ADR-0049 C1): `--patch FILE` registers the source as a source of the
workspace (`--workspace`, or `workspace:` in toprope.yaml; a new workspace file is made) and
writes the elements as a patch, joined to the workspace's draft, for

    toprope-change "import from <source>" --patch FILE --workspace W --draft <domain>

which proposes them, checks the working copy, and asks a person to confirm them from one diff.

The kind names an extractor (a format), `--via` a reader (where the source lives; `mcp` lists a
server's tools from its command or URL); both are ports that installed packages extend.
`--profile` holds a team's conventions: which fields are stages, where roles come from, what to
ignore or rename. Every element written is `proposed`, citing its place. A draft that joins an
existing one never overwrites it: each disagreement is a conflict naming both places. Then the
command prints what the source cannot say; `--questions` writes it as records an agent works from
(`id`, `kind`, `text`, `decides`, `places`, `quote`, `modality`), which `toprope-run
ask_question` puts in the interview. A person confirms what is right (ADR-0041).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from ..errors import fixed
from . import Profile, apply, import_source, kinds


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-import", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", nargs="?", help="the source's format: an extractor (see --list)")
    ap.add_argument("source", nargs="?", help="where the source is, as the reader takes it (a path, a URL, a command)")
    ap.add_argument("--via", help="the reader that reaches the source (default: mcp for mcp, else file)")
    ap.add_argument("--profile", help="a YAML file of the team's conventions")
    ap.add_argument("--domain", default="imported", help="the new domain's name")
    ap.add_argument("--out", help="where to write a new draft (default: <domain>.domain.yaml here)")
    ap.add_argument("--into", help="an existing draft to join this source to; its elements are never overwritten")
    ap.add_argument("--patch", help="write the elements as a patch for `toprope-change --patch`, and register the "
                                    "source in the workspace, instead of writing a draft")
    ap.add_argument("--workspace", help="with --patch: the workspace file (default: `workspace:` in toprope.yaml); "
                                        "a new one is made for --domain")
    ap.add_argument("--source-id", help="with --patch: the source's id in the workspace (default: <domain>-<kind>)")
    ap.add_argument("--binding-out", help="write the draft binding a server's tools give (mcp), for toprope-proxy")
    ap.add_argument("--questions", help="also write the conflicts and questions as YAML records, for an agent to work from")
    ap.add_argument("--list", action="store_true", help="the readers and extractors installed")
    return ap


def _new(path: str | None, flag: str) -> Path | None:
    if path and Path(path).exists():
        raise SystemExit(fixed(f"{path} exists", f"give {flag} a new file"))
    return Path(path) if path else None


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    if a.list or not (a.kind and a.source):
        k = kinds()
        print(f"readers: {', '.join(k['readers'])}\nextractors: {', '.join(k['extractors'])}")
        if not a.list:
            raise SystemExit(fixed("no source given", "give `toprope-import <extractor> <source>`"))
        return
    if a.patch and (a.into or a.out):
        raise SystemExit(fixed("--patch joins the workspace's draft, so it takes no --into or --out",
                               "give --patch alone (the loop proposes into the workspace's draft), or --into/--out "
                               "to write a file"))
    if a.into and a.out:
        raise SystemExit(fixed("--into and --out both name where the draft goes", "give one"))
    if (a.workspace or a.source_id) and not a.patch:
        raise SystemExit(fixed("--workspace and --source-id go with --patch", "add --patch FILE, or leave them out"))
    qdest, bdest, pdest = _new(a.questions, "--questions"), _new(a.binding_out, "--binding-out"), _new(a.patch, "--patch")
    named = [p.resolve() for p in (qdest, bdest, pdest, Path(a.out) if a.out else None, Path(a.into) if a.into else None)
             if p is not None]
    if len(named) != len(set(named)):
        raise SystemExit(fixed("two options name the same file", "give each its own file"))
    base, ws = None, None
    if a.into:
        try:
            base = yaml.safe_load(Path(a.into).read_text())
        except (OSError, yaml.YAMLError) as e:
            raise SystemExit(fixed(f"cannot read the draft {a.into}: {e}", "give --into an existing draft, or --out "
                                   "for a new one")) from None
        if not isinstance(base, dict) or "domain" not in base:
            raise SystemExit(fixed(f"{a.into} is not a declaration", "give --into a `*.domain.yaml` draft"))
    if a.patch:
        from .loop import workspace_file
        ws = workspace_file(a.workspace)
        if ws.exists():
            from ..workspace import Workspace
            base = Workspace(ws).draft()
        else:
            base = {"domain": a.domain, "version": 1}
    try:
        out = import_source(a.kind, a.source, domain=str(base["domain"]) if base else a.domain,
                            profile=Profile.load(a.profile), via=a.via, into=base)
    except (yaml.YAMLError, ValueError, UnicodeDecodeError) as e:
        raise SystemExit(fixed(f"{a.source} does not read as {a.kind}: {e}",
                               "give the export as it was written, or another extractor")) from None
    draft = out["draft"]
    has_draft = bool(draft["objects"] or draft["actions"])
    if not has_draft and not out["questions"] and not out["conflicts"]:
        raise SystemExit(fixed(f"nothing to import from {a.source}",
                               f"check that it is {a.kind}: no things, enums, statuses or rules were found"))
    if bdest and out["binding"] is None:
        raise SystemExit(fixed(f"the {a.kind} extractor drafts no binding", "--binding-out goes with `mcp`, which "
                               "reads a server's tools"))
    dest = Path(a.into or a.out or f"{draft['domain']}.domain.yaml")
    if has_draft and not (a.into or a.patch) and dest.exists():      # every check before anything is written
        raise SystemExit(fixed(f"{dest} exists", "give --out a new file, or --into it to join this source to the draft"))
    if a.patch and not out["items"] and not has_draft:
        raise SystemExit(fixed(f"nothing to propose from {a.source}: it names no element",
                               "work from its questions (--questions); an agent proposes elements from the answers"))
    if a.patch and not out["items"]:
        raise SystemExit(fixed(f"nothing to propose from {a.source}: the draft already says all of it",
                               "nothing to do; any conflict with the draft is for the interview (--questions)"))
    reg = None
    if a.patch:                                                   # its checks too run before anything is written
        from .loop import plan_registration, source_kind
        reg = plan_registration(ws, out["raw"], a.source_id or f"{draft['domain']}-{a.kind}", source_kind(out["raw"]),
                                draft["domain"])
    joined = None
    if a.into:
        from . import _check
        joined = apply(base, out["items"])
        _check(joined, a.kind)
    if qdest:
        qdest.parent.mkdir(parents=True, exist_ok=True)
        qdest.write_text(yaml.safe_dump({"source": a.source,
                                         "conflicts": [n.as_dict() for n in out["conflict_records"]],
                                         "questions": [n.as_dict() for n in out["question_records"]]},
                                        sort_keys=False, allow_unicode=True, width=100))
    if bdest:
        from .extractors.mcp import render_binding
        bdest.parent.mkdir(parents=True, exist_ok=True)
        bdest.write_text(render_binding(out["binding"], draft["domain"]))
        print(f"wrote {bdest}: a draft binding; the proxy serves it once a person confirms it (--confirm-binding)")
    if reg is not None:
        _patch(a, ws, out, reg)
    elif joined is not None:
        dest.write_text(yaml.safe_dump(joined, sort_keys=False, allow_unicode=True))
        print(f"joined {a.source} into {dest}: {len(out['items'])} element(s) added, each proposed and citing its "
              f"place; {len(out['conflicts'])} conflict(s), where the draft's own was kept")
    elif has_draft:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(yaml.safe_dump(draft, sort_keys=False, allow_unicode=True))
        print(f"wrote {dest}: {len(draft['objects'])} thing(s), {len(draft['actions'])} action(s), "
              f"{len(draft['transitions'])} with stages; every element is proposed, citing {a.source}")
    else:
        print(f"no draft written: {a.source} names nothing to declare yet; {len(out['questions'])} question(s) and "
              f"{len(out['conflicts'])} conflict(s) for the interview")
    for title, items in (("conflicts in the source", out["conflicts"]), ("questions for the interview", out["questions"])):
        if items:
            print(f"\n{title}:")
            for q in items:
                print(f"  - {q}")


def _patch(a: argparse.Namespace, ws: Path, out: dict, reg) -> None:
    from .loop import cites, source_kind, write_patch
    domain = out["draft"]["domain"]
    reg.apply()
    made, rel = reg.made, reg.rel
    sid = a.source_id or f"{domain}-{a.kind}"
    kind = source_kind(out["raw"])
    write_patch(Path(a.patch), out["items"], cites(ws, sid, out["raw"], out["items"]), f"S-{sid}")
    from ..workspace import Workspace
    decl = Workspace(ws).domain_path
    try:
        decl = decl.relative_to(ws.resolve().parent)
    except ValueError:
        pass
    print(f"wrote {a.patch}: {len(out['items'])} element(s) to propose, each citing the source {sid} "
          f"({rel}, registered in {ws})" + (f"; made the workspace {ws}" if made else ""))
    print("\nnext, into the change loop:")
    if made:
        print(f"  toprope-run open_draft {domain} --domain-id {domain} --declaration {decl} --branch work")
    print(f"  toprope-run add_source S-{sid} --kind {kind} --path {rel}")
    print(f"  toprope-change \"import from {a.source}\" --patch {a.patch} --workspace {ws} --draft {domain}")


__all__ = ["build_parser", "main"]
