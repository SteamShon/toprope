"""Source readers with redaction and local-only sources (ADR-0014 §6).

A source is raw material for drafting: the repository (code, schema), markdown records,
session transcripts, or the interview log. Readers split it into chunks with a stable `ref`
(`<source id>:<path>#L<a>-L<b>`) that a drafted element cites as its `source`.

Every chunk is redacted before anyone reads it: secrets (keys, tokens, private keys,
password assignments) and personal data (emails, phone numbers, resident registration
numbers). A source marked `local_only` is never served to a hosted model: the authoring
tools list it but refuse its content. Paths matching `exclude` (by default everything under
`experiments/`: the instruments and the guides that describe them) are never read at all.
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Kind = Literal["repository", "records", "transcripts", "interview-log"]
# Source kind → the `source.kind` a drafted element records (docs/domain-schema.md).
ELEMENT_KIND = {"repository": "system", "records": "record", "transcripts": "record", "interview-log": "interview"}
# Experiment material is never source material: the held-out gold and its key, and the
# guides and templates that reveal what the gold probes.
DEFAULT_EXCLUDE = (".git/**", ".venv/**", "**/node_modules/**", "**/__pycache__/**", "experiments/**")
DEFAULT_GLOBS = {
    "repository": ["**/*.py", "**/*.sql", "**/*.json", "**/*.yaml", "**/*.yml", "**/*.toml"],
    "records": ["**/*.md"],
    "transcripts": ["**/*.jsonl", "**/*.md", "**/*.txt"],
    "interview-log": ["**/*.jsonl"],
}
MAX_FILE_BYTES = 512 * 1024
CODE_CHUNK_LINES = 120


@dataclass(frozen=True)
class SourceSpec:
    id: str
    kind: Kind
    path: str                                   # file or directory, relative to the workspace root
    globs: tuple[str, ...] = ()
    local_only: bool = False
    exclude: tuple[str, ...] = ()
    url: str | None = None                      # a link: fetched once into `path` (a snapshot)


@dataclass(frozen=True)
class Chunk:
    ref: str
    source: str
    text: str
    redactions: dict[str, int] = field(default_factory=dict, hash=False)


# -- redaction ---------------------------------------------------------------------------------
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("api-key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*")),
    ("assignment", re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)"
                              r"(\s*[:=]\s*)(['\"]?)([^\s'\"]{6,})\3")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("resident-id", re.compile(r"\b\d{6}-[1-4]\d{6}\b")),
    ("phone", re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s-]\d{3,4}[\s-]\d{4}(?![\w.])")),
]


def redact(text: str, extra: list[tuple[str, re.Pattern]] | None = None) -> tuple[str, dict[str, int]]:
    """Replace secrets and personal data with `[REDACTED:<kind>]`; return the counts."""
    counts: dict[str, int] = {}
    for kind, pat in PATTERNS + (extra or []):
        def sub(m: re.Match, kind=kind) -> str:
            counts[kind] = counts.get(kind, 0) + 1
            if kind == "assignment":   # keep the name, drop the value
                return f"{m.group(1)}{m.group(2)}[REDACTED:secret]"
            return f"[REDACTED:{kind}]"
        text = pat.sub(sub, text)
    return text, counts


# -- readers -----------------------------------------------------------------------------------
def _matches(rel: str, patterns) -> bool:
    return any(fnmatch.fnmatch(rel, p) or (p.startswith("**/") and fnmatch.fnmatch(rel, p[3:])) for p in patterns)


def files(spec: SourceSpec, root: Path, exclude: tuple[str, ...] = DEFAULT_EXCLUDE) -> list[Path]:
    base = (root / spec.path).resolve()
    rootr = root.resolve()
    if not base.is_relative_to(rootr):
        raise ValueError(f"source {spec.id}: {spec.path} is outside the workspace")
    cands = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
    globs = spec.globs or tuple(DEFAULT_GLOBS[spec.kind])
    out = []
    for p in cands:
        rel = p.relative_to(rootr).as_posix()
        if _matches(rel, exclude + spec.exclude) or p.is_symlink():
            continue
        if (base.is_file() or _matches(p.relative_to(base).as_posix(), globs)) and p.stat().st_size <= MAX_FILE_BYTES:
            out.append(p)
    return out


def _text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None   # binary or unreadable: skipped


def _by_lines(lines: list[str], size: int):
    for i in range(0, len(lines), size):
        yield i + 1, min(i + size, len(lines)), "\n".join(lines[i:i + size])


def _by_headings(lines: list[str]):
    starts = [i for i, l in enumerate(lines) if re.match(r"#{1,3} ", l)] or [0]
    if starts[0] != 0:
        starts.insert(0, 0)
    for k, a in enumerate(starts):
        b = starts[k + 1] if k + 1 < len(starts) else len(lines)
        body = "\n".join(lines[a:b]).strip()
        if body:
            yield a + 1, b, body


def _message_text(m: dict) -> str | None:
    msg = m.get("message", m)
    role = msg.get("role") or m.get("type") or m.get("role")
    content = msg.get("content")
    if isinstance(content, list):
        content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    if role not in ("user", "assistant", "human") or not isinstance(content, str) or not content.strip():
        return None
    return f"{role}: {content.strip()}"


def _jsonl(lines: list[str], interview: bool):
    for n, line in enumerate(lines, 1):
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if not isinstance(m, dict):
            continue
        if interview:
            text = "\n".join(f"{k}: {m[k]}" for k in ("question", "answer", "decisions") if m.get(k))
        else:
            text = _message_text(m)
        if text:
            yield n, n, text


def read(spec: SourceSpec, root: Path, extra_redactions=None, exclude: tuple[str, ...] = DEFAULT_EXCLUDE) -> list[Chunk]:
    """All chunks of a source, redacted. Callers decide whether local-only content may leave."""
    out = []
    for p in files(spec, root, exclude):
        text = _text(p)
        if text is None:
            continue
        lines = text.splitlines()
        rel = p.relative_to(root.resolve()).as_posix()
        if spec.kind == "repository":
            parts = _by_lines(lines, CODE_CHUNK_LINES)
        elif p.suffix == ".jsonl":
            parts = _jsonl(lines, spec.kind == "interview-log")
        else:
            parts = _by_headings(lines)
        for a, b, body in parts:
            red, counts = redact(body, extra_redactions)
            ref = f"{spec.id}:{rel}#L{a}" + (f"-L{b}" if b != a else "")
            out.append(Chunk(ref, spec.id, red, counts))
    return out


# -- links ---------------------------------------------------------------------------------------
MAX_FETCH_BYTES = 2 * 1024 * 1024
SNAPSHOTS = ".toprope/snapshots"


class FetchError(Exception):
    pass


def _html_to_text(html: str) -> str:
    import html as h
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", html)
    html = re.sub(r"(?i)<h([1-3])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", html)
    text = h.unescape(re.sub(r"<[^>]+>", " ", html))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def fetch(spec: SourceSpec, root: Path, timeout: float = 20) -> dict:
    """Fetch a link source once into its snapshot directory (`path`). The snapshot is what the
    readers read, so every chunk is redacted like any other file, and refs stay stable."""
    import hashlib
    import urllib.request
    from datetime import datetime, timezone
    if not spec.url or not spec.url.lower().startswith(("http://", "https://")):
        raise FetchError(f"source {spec.id}: only http(s) links can be fetched")
    if spec.kind not in ("records", "transcripts"):
        raise FetchError(f"source {spec.id}: a link can be a records or transcripts source; "
                         "clone a repository and give its path instead")
    req = urllib.request.Request(spec.url, headers={"User-Agent": "toprope-author/0", "Accept": "text/*, application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final = r.geturl()
            if not final.lower().startswith(("http://", "https://")):
                raise FetchError(f"source {spec.id}: redirected to a non-http(s) address")
            ctype = r.headers.get("Content-Type", "")
            body = r.read(MAX_FETCH_BYTES + 1)
    except FetchError:
        raise
    except Exception as e:
        raise FetchError(f"source {spec.id}: could not fetch {spec.url} ({type(e).__name__}: {e}). "
                         "A private document (behind a login) cannot be fetched: download it into the "
                         "workspace and give its path instead.") from None
    if len(body) > MAX_FETCH_BYTES:
        raise FetchError(f"source {spec.id}: larger than {MAX_FETCH_BYTES} bytes")
    if not (ctype.startswith("text/") or "json" in ctype or "xml" in ctype or not ctype):
        raise FetchError(f"source {spec.id}: not text ({ctype})")
    text = body.decode("utf-8", errors="replace")
    if "html" in ctype or text.lstrip()[:15].lower().startswith(("<!doctype html", "<html")):
        text = _html_to_text(text)
    out = (root / spec.path).resolve()
    if not out.is_relative_to(root.resolve()):
        raise FetchError(f"source {spec.id}: snapshot path outside the workspace")
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.md").write_text(text)
    meta = {"url": spec.url, "final_url": final, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "content_type": ctype, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
    (out / "snapshot.json").write_text(json.dumps(meta, indent=2))
    return meta


__all__ = ["DEFAULT_EXCLUDE", "ELEMENT_KIND", "SNAPSHOTS", "Chunk", "FetchError", "SourceSpec", "fetch", "files",
           "read", "redact"]
