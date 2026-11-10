"""An import into theme 1's change loop (ADR-0049 C1, ADR-0051): the source becomes a workspace
source, so every element's citation resolves, and the elements become a patch for
`toprope-change "<intent>" --patch FILE`, which proposes them, checks the working copy and asks a
person to confirm them from one diff.

A source that is a file inside the workspace is registered where it is. Anything else (a file
elsewhere, a URL, an MCP server's tool list) is kept as a snapshot under
`.toprope/imports/<source id>/`, which is what the elements cite."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from ..errors import fixed
from .draft import Item
from .port import Raw

IMPORTS = ".toprope/imports"


def workspace_file(given: str | None) -> Path:
    if given:
        return Path(given)
    from ..adapters.cli import CONFIG, read_config
    if Path(CONFIG).is_file() and (ws := read_config(Path(CONFIG)).get("workspace")):
        return Path(str(ws))
    raise SystemExit(fixed("no workspace to register the source in",
                           "give --workspace (a `*.workspace.yaml` file; a new one is made), or set `workspace:` in "
                           "toprope.yaml"))


def ensure_workspace(path: Path, domain: str) -> bool:
    """A new workspace for `domain`: its declaration `<domain>.domain.yaml` beside it, and its logs.
    Returns whether it was made."""
    if path.exists():
        return False
    if not path.name.endswith(".workspace.yaml"):
        raise SystemExit(fixed(f"{path} is not a workspace file", "name it `<something>.workspace.yaml`"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# The workspace of {domain}'s declaration (made by toprope-import): its sources and logs.\n"
                    f"domain: {domain}.domain.yaml\n"
                    f"interview_log: {domain}.interview.jsonl\n"
                    f"usage_log: {domain}.sources-used.jsonl\n")
    return True


def register(ws_path: Path, raw: Raw, source_id: str, kind: str) -> str:
    """Make the source one of the workspace's sources (`sources:` in its file) and return its path
    there. An id already registered for the same path is kept; for another path it is refused."""
    root = ws_path.resolve().parent
    src = Path(raw.ref)
    if raw.parts is None and src.is_file() and src.resolve().is_relative_to(root):
        rel = src.resolve().relative_to(root).as_posix()
    else:
        name = src.name if raw.parts is None and src.is_file() else "source.json" if kind == "repository" else "source.md"
        rel = f"{IMPORTS}/{source_id}/{name}"
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw.data)
    text = ws_path.read_text()
    cfg = yaml.safe_load(text) or {}
    have = next((s for s in cfg.get("sources") or [] if isinstance(s, dict) and s.get("id") == source_id), None)
    if have is not None:
        if have.get("path") != rel:
            raise SystemExit(fixed(f"the workspace {ws_path} already has a source {source_id!r}, at {have.get('path')}",
                                   "give --source-id a new id for this source"))
        return rel
    entry = f"{{id: {json.dumps(source_id)}, kind: {kind}, path: {json.dumps(rel)}}}"
    lines = text.splitlines()
    at = next((i for i, ln in enumerate(lines) if re.match(r"^sources:\s*(#.*)?$", ln)), None)
    if at is None:
        lines += ["sources:", f"  - {entry}"]
    else:
        end = at + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t", "-")):
            end += 1
        first = next((ln for ln in lines[at + 1:end] if ln.lstrip().startswith("- ")), "  - ")
        indent = first[:len(first) - len(first.lstrip())]
        while end > at + 1 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, f"{indent}- {entry}")
    new = "\n".join(lines) + "\n"
    if not any(isinstance(s, dict) and s.get("id") == source_id for s in (yaml.safe_load(new) or {}).get("sources") or []):
        raise SystemExit(fixed(f"could not add the source to {ws_path}: its `sources:` is not a list this can extend",
                               f"add `- {entry}` under `sources:` yourself, then import again"))
    ws_path.write_text(new)
    return rel


def line_of(place: str, ref: str, text: str) -> int:
    """The line a place (`<ref>#L12`, or `<ref>#/json/pointer`) is on in the source's text; 1 if it
    cannot be found."""
    frag = place[len(ref) + 1:] if place.startswith(ref + "#") else place.rpartition("#")[2]
    if m := re.match(r"L(\d+)", frag):
        return int(m.group(1))
    if not frag.startswith("/"):
        return 1
    try:
        node = yaml.compose(text)
    except yaml.YAMLError:
        return 1
    line = 1
    for seg in frag[1:].split("/"):
        seg = seg.replace("~1", "/").replace("~0", "~")
        if isinstance(node, yaml.MappingNode):
            hit = next(((k, v) for k, v in node.value if getattr(k, "value", None) == seg), None)
            if hit is None:
                break
            line, node = hit[0].start_mark.line + 1, hit[1]
        elif isinstance(node, yaml.SequenceNode) and seg.isdigit() and int(seg) < len(node.value):
            node = node.value[int(seg)]
            line = node.start_mark.line + 1
        else:
            break
    return line


def cites(ws_path: Path, source_id: str, raw: Raw, items: list[Item]) -> list[str]:
    """For each item, the workspace chunk its place is in: a ref `propose_element` resolves."""
    from ..workspace import Workspace
    chunks = Workspace(ws_path).chunks(source_id)
    if not chunks:
        raise SystemExit(fixed(f"the source {source_id} has no text the workspace can read",
                               "import a text source (the workspace skips binary files and files over 512 KiB)"))
    spans = []
    for c in chunks:
        m = re.search(r"#L(\d+)(?:-L(\d+))?$", c.ref)
        a = int(m.group(1)) if m else 1
        spans.append((a, int(m.group(2)) if m and m.group(2) else a, c.ref))
    text = raw.data.decode("utf-8", "replace")
    out = []
    for it in items:
        n = line_of(it.ref, raw.ref, text)
        out.append(next((r for a, b, r in spans if a <= n <= b), spans[0][2]))
    return out


def write_patch(path: Path, items: list[Item], refs: list[str], origin: str) -> None:
    """The patch `toprope-change --patch` takes: each element's path, value, citation and origin,
    with the exact place in the source it was read from."""
    body = [{"path": it.path, "value": it.value, "cites": r, "origin": origin, "place": it.ref}
            for it, r in zip(items, refs)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=100))


def source_kind(raw: Raw) -> str:
    """The workspace source kind: written rules are records; anything else is the system's."""
    return "records" if Path(raw.ref).suffix.lower() in (".md", ".markdown") or raw.parts else "repository"


__all__ = ["cites", "ensure_workspace", "line_of", "register", "source_kind", "workspace_file", "write_patch"]
