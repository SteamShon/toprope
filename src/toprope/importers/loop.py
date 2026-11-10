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
from dataclasses import dataclass
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


def new_workspace(path: Path, domain: str) -> str:
    """The text of a new workspace for `domain`: its declaration `<domain>.domain.yaml` beside it,
    and its logs."""
    if not path.name.endswith(".workspace.yaml"):
        raise SystemExit(fixed(f"{path} is not a workspace file", "name it `<something>.workspace.yaml`"))
    return (f"# The workspace of {domain}'s declaration (made by toprope-import): its sources and logs.\n"
            f"domain: {domain}.domain.yaml\n"
            f"interview_log: {domain}.interview.jsonl\n"
            f"usage_log: {domain}.sources-used.jsonl\n")


@dataclass
class Registration:
    """What registering a source writes, decided before anything is written: the workspace's new
    text (None: unchanged), the snapshot (None: the source is a file in the workspace), and the
    source's path there."""
    ws_path: Path
    rel: str
    text: str | None
    snapshot: bytes | None
    made: bool

    def apply(self) -> None:
        if self.snapshot is not None:
            dest = self.ws_path.resolve().parent / self.rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.snapshot)
        if self.text is not None:
            self.ws_path.parent.mkdir(parents=True, exist_ok=True)
            self.ws_path.write_text(self.text)


def plan_registration(ws_path: Path, raw: Raw, source_id: str, kind: str, domain: str) -> Registration:
    """Make the source one of the workspace's sources (`sources:` in its file). Every check runs
    here, before anything is written: an id registered for another path, or holding a snapshot
    with other content, is refused, and so is a workspace file that would not read back."""
    from ..decl import load_yaml
    made = not ws_path.exists()
    text = new_workspace(ws_path, domain) if made else ws_path.read_text()
    root = ws_path.resolve().parent
    src = Path(raw.ref)
    snapshot: bytes | None = None
    if raw.parts is None and src.is_file() and src.resolve().is_relative_to(root):
        rel = src.resolve().relative_to(root).as_posix()
    else:
        name = src.name if raw.parts is None and src.is_file() else "source.json" if kind == "repository" else "source.md"
        rel, snapshot = f"{IMPORTS}/{source_id}/{name}", raw.data
        dest = root / rel
        if dest.exists() and dest.read_bytes() != raw.data:
            raise SystemExit(fixed(f"the source {source_id!r} already holds a different snapshot ({rel}): the "
                                   "source changed since it was imported, and the elements proposed from it cite "
                                   "the old one", "give --source-id a new id for this version of the source"))
    try:
        cfg = load_yaml(text) or {}
    except (ValueError, yaml.YAMLError) as e:
        raise SystemExit(fixed(f"the workspace {ws_path} does not read: {e}", "fix the file, then import again")) from None
    have = next((s for s in cfg.get("sources") or [] if isinstance(s, dict) and s.get("id") == source_id), None)
    if have is not None:
        if have.get("path") != rel:
            raise SystemExit(fixed(f"the workspace {ws_path} already has a source {source_id!r}, at {have.get('path')}",
                                   "give --source-id a new id for this source"))
        return Registration(ws_path, rel, text if made else None, snapshot, made)
    entry = {"id": source_id, "kind": kind, "path": rel}
    flow = f"{{id: {json.dumps(source_id)}, kind: {kind}, path: {json.dumps(rel)}}}"
    lines = text.splitlines()
    block = next((i for i, ln in enumerate(lines) if re.match(r"^sources:\s*(#.*)?$", ln)), None)
    inline = next((i for i, ln in enumerate(lines) if re.match(r"^sources:\s*\[.*\]\s*(#.*)?$", ln)), None)
    if block is not None:
        end = block + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t", "-")):
            end += 1
        first = next((ln for ln in lines[block + 1:end] if ln.lstrip().startswith("- ")), "  - ")
        indent = first[:len(first) - len(first.lstrip())]
        while end > block + 1 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, f"{indent}- {flow}")
    elif inline is not None:                                       # `sources: [...]` on one line
        lines[inline] = f"sources: {json.dumps([*(cfg.get('sources') or []), entry])}"
    elif "sources" in cfg:
        raise SystemExit(fixed(f"the workspace {ws_path} writes `sources:` in a form this cannot extend",
                               f"write it as a block list, or add `- {flow}` under it yourself, then import again"))
    else:
        lines += ["sources:", f"  - {flow}"]
    new = "\n".join(lines) + "\n"
    try:
        after = load_yaml(new) or {}
    except (ValueError, yaml.YAMLError) as e:
        after = {"error": str(e)}
    if after.get("sources") != [*(cfg.get("sources") or []), entry] or \
            {k: v for k, v in after.items() if k != "sources"} != {k: v for k, v in cfg.items() if k != "sources"}:
        raise SystemExit(fixed(f"could not add the source to {ws_path} so that it reads back",
                               f"add `- {flow}` under `sources:` yourself, then import again"))
    return Registration(ws_path, rel, new, snapshot, made)


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


__all__ = ["Registration", "cites", "line_of", "new_workspace", "plan_registration", "source_kind", "workspace_file",
           "write_patch"]
