"""M2's held-out items for ②: checked, sealed and later unsealed without an agent seeing them.

  python experiments/tools/m2_heldout.py guide          # what to write about, and in what form
  python experiments/tools/m2_heldout.py ask FILE       # answer fixed questions at a terminal; writes FILE
  python experiments/tools/m2_heldout.py notes NOTES    # a rules memo with its guide, to fill first
  python experiments/tools/m2_heldout.py ask FILE --from NOTES   # turn each memo line into an item
  python experiments/tools/m2_heldout.py validate FILE   # the format; prints counts and errors only
  python experiments/tools/m2_heldout.py seal FILE       # writes experiments/m2/heldout.sealed.json
  python experiments/tools/m2_heldout.py unseal FILE     # after Phase A: checks the hash, copies it in

The filled file lives outside the repository (`heldout.template.yaml` says where). Every command
prints only counts, ids and errors that name a field; it never prints a question or an answer, so
an agent may run `validate` for the researcher. `seal` refuses a file inside the repository. The
sealed record holds the file's sha256, the number of items and their ids, and nothing else. The
researcher commits it before the interview starts. `unseal` copies the file to
`experiments/m2/heldout.yaml` only when its sha256 is the sealed one, so the items scored are the
items sealed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
import sys
from pathlib import Path

import yaml

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
M2 = ROOT / "experiments" / "m2"
SEALED = M2 / "heldout.sealed.json"
KINDS = {"yes_no", "outcome", "state", "actors", "free_text"}
MIN_ITEMS = 12


def die(msg: str, fix: str) -> None:
    raise SystemExit(f"error: {msg}. Fix: {fix}")


def placeholder(v: object) -> bool:
    return isinstance(v, str) and v.strip().startswith("<") and v.strip().endswith(">")


def problems(doc: object) -> list[str]:
    """Format errors, naming ids and fields only, never content."""
    if not isinstance(doc, dict) or doc.get("instrument") != "heldout" or doc.get("experiment") != "M2":
        return ["the file is not M2's held-out items (`instrument: heldout`, `experiment: M2`)"]
    out = []
    items = doc.get("items")
    if not isinstance(items, list) or not items:
        return ["`items` is an empty list"]
    seen = set()
    for n, it in enumerate(items, 1):
        where = f"item {n}"
        if not isinstance(it, dict):
            out.append(f"{where}: not a mapping")
            continue
        iid = it.get("id")
        where = f"item {iid or n}"
        if not iid or iid in seen:
            out.append(f"{where}: `id` is missing or repeated")
        seen.add(iid)
        if not isinstance(it.get("question"), str) or not it["question"].strip() or placeholder(it["question"]):
            out.append(f"{where}: `question` is empty or still the placeholder")
        ans = it.get("answer")
        if not isinstance(ans, dict) or ans.get("kind") not in KINDS:
            out.append(f"{where}: `answer.kind` is one of {sorted(KINDS)}")
            continue
        kind, exp = ans["kind"], ans.get("expected")
        if kind == "yes_no" and exp not in ("yes", "no"):
            out.append(f"{where}: a yes_no answer expects yes or no")
        elif kind == "outcome" and not (isinstance(exp, dict) and exp.get("result") in ("allowed", "denied")):
            out.append(f"{where}: an outcome answer expects {{result: allowed|denied}}")
        elif kind == "state" and (not isinstance(exp, str) or not exp.strip() or placeholder(exp)):
            out.append(f"{where}: a state answer expects the resulting state")
        elif kind == "actors" and not (isinstance(exp, list) and exp and all(isinstance(a, str) and a for a in exp)):
            out.append(f"{where}: an actors answer expects a list of roles or actors")
        elif kind == "free_text" and not (isinstance(ans.get("rubric"), list) and ans["rubric"]):
            out.append(f"{where}: a free_text answer expects a `rubric` list")
        if not isinstance(it.get("tacit"), bool):
            out.append(f"{where}: `tacit` is true or false")
    return out


def load(path: Path) -> tuple[bytes, dict]:
    try:
        data = path.expanduser().read_bytes()
    except OSError as e:
        die(f"cannot read {path}: {e.strerror}", "give the filled held-out file")
    return data, yaml.safe_load(data) or {}


def inside_repo(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def summary(doc: dict) -> str:
    items = doc.get("items") or []
    tacit = sum(1 for i in items if isinstance(i, dict) and i.get("tacit") is True)
    kinds: dict[str, int] = {}
    for i in items:
        k = (i.get("answer") or {}).get("kind") if isinstance(i, dict) else None
        kinds[str(k)] = kinds.get(str(k), 0) + 1
    return f"{len(items)} items, {tacit} tacit; kinds {dict(sorted(kinds.items()))}"


def cmd_validate(a: argparse.Namespace) -> None:
    _, doc = load(Path(a.file))
    found = problems(doc)
    for p in found:
        print(f"error: {p}")
    print(summary(doc) if isinstance(doc, dict) else "")
    if len(doc.get("items") or []) < MIN_ITEMS:
        print(f"note: fewer than {MIN_ITEMS} items; ②'s observation will be reported as small")
    if found:
        raise SystemExit(1)


def cmd_seal(a: argparse.Namespace, sealed: Path = SEALED) -> None:
    path = Path(a.file)
    if inside_repo(path):
        die(f"{path} is inside the repository, where an agent or a commit could read it",
            "keep the filled file outside the repository, e.g. ~/m2-private/heldout.yaml")
    if sealed.exists():
        die(f"{sealed} exists: the held-out items are sealed once", "keep the sealed file; do not reseal")
    data, doc = load(path)
    found = problems(doc)
    if found:
        die(f"{len(found)} format error(s)", "run `validate` and fix them")
    ids = [str(i["id"]) for i in doc["items"]]
    sealed.write_text(json.dumps({"sha256": hashlib.sha256(data).hexdigest(), "items": len(ids), "ids": ids,
                                  "sealed_at": datetime.now(UTC).isoformat(timespec="seconds")}, indent=2) + "\n")
    print(f"sealed {len(ids)} items in {sealed}; commit it yourself before the interview starts")


def cmd_unseal(a: argparse.Namespace, sealed: Path = SEALED, into: Path = M2 / "heldout.yaml") -> None:
    try:
        rec = json.loads(sealed.read_text())
    except (OSError, ValueError):
        die(f"cannot read {sealed}", "seal the items first, and commit the record")
    data, _ = load(Path(a.file))
    if hashlib.sha256(data).hexdigest() != rec["sha256"]:
        die("the file's sha256 differs from the sealed one", "give the file exactly as it was sealed")
    into.write_bytes(data)
    print(f"unsealed {rec['items']} items into {into}; commit it with the scoring")


def _outside(path: Path) -> Path:
    path = path.expanduser()
    if inside_repo(path):
        die(f"{path} is inside the repository, where an agent or a commit could read it",
            "keep it outside the repository, e.g. in ~/m2-private/")
    return path


def cmd_guide(a: argparse.Namespace) -> None:
    from m2_heldout_ask import GUIDE
    print(GUIDE)


def cmd_notes(a: argparse.Namespace) -> None:
    from m2_heldout_ask import write_notes
    path = _outside(Path(a.file))
    write_notes(path)
    print(f"{path}: write one rule per line, then `ask FILE --from {path}`")


def cmd_ask(a: argparse.Namespace, ask=input, say=print, terminal=None) -> None:
    from m2_heldout_ask import GUIDE, Asker, at_terminal, read_notes
    if not (at_terminal() if terminal is None else terminal):
        die("`ask` runs only at a terminal, so that only a person answers",
            "run it yourself in a terminal; an agent may run `validate` instead")
    path = _outside(Path(a.file))
    if getattr(a, "from_notes", None):
        _outside(Path(a.from_notes))
    say(GUIDE)
    rules = read_notes(Path(a.from_notes)) if getattr(a, "from_notes", None) else None
    Asker(path, ask=ask, say=say).run(rules)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="m2_heldout", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, f in (("validate", cmd_validate), ("seal", cmd_seal), ("unseal", cmd_unseal),
                    ("notes", cmd_notes), ("ask", cmd_ask)):
        s = sub.add_parser(name)
        s.add_argument("file")
        if name == "ask":
            s.add_argument("--from", dest="from_notes", help="a rules memo made with `notes`")
        s.set_defaults(f=f)
    sub.add_parser("guide").set_defaults(f=cmd_guide)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
