"""The workspace (ADR-0014, ADR-0017, ADR-0037): draft a declaration from sources, interview its
owner, and confirm. Kernel: every domain's authoring uses it, through kernel services.

Rules it enforces:
- every drafted element cites a real source chunk (`source.ref`), so no rule is unsupported
- agents write only `proposed`: `propose` and `answer` never set `confirmed`
- only a person confirms: `confirm` is called with the channel the confirmation came
  through (`terminal`: the owner's own terminal; `kernel`: a declared action the kernel
  checked was taken by that person), and each confirmation is logged with that channel and who
- local-only sources are listed but their content is never served
- the interview log records every question, answer quote and decision; the usage log
  records which source chunks were served (the drafter records which sources it used)
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..decl import Domain, load_yaml, validate_domain
from ..sources import (
    DEFAULT_EXCLUDE,
    ELEMENT_KIND,
    SNAPSHOTS,
    Chunk,
    FetchError,
    SourceSpec,
    fetch,
    read,
    stale,
)
from ..errors import fixed

CONFIG = "toprope.workspace.yaml"
LIST_BY_ID = {"invariants", "preconditions", "scenarios"}
UNDECIDED = "undecided"


class AuthoringError(ValueError):
    pass


@dataclass
class Question:
    id: str
    kind: str          # purpose | default | row | conflict | confirm
    text: str
    decides: list[str]  # element paths the answer would settle
    priority: float

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "text": self.text, "decides": self.decides,
                "priority": self.priority}



CHANNELS = ("terminal", "kernel")      # how a person confirms or approves (the MCP elicitation is gone)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def element_path(path: str) -> list[str]:
    segs = path.split(".")
    if not path or any(not s for s in segs):
        raise AuthoringError(fixed(f"bad element path {path!r}", "write the path as dot-separated names, such as `actions.approve.preconditions`"))
    return segs


def is_element(segs: list[str]) -> bool:
    """Paths whose value carries `source` and `status` (Provenance in decl/models.py)."""
    return ((len(segs) == 2 and segs[0] in ("objects", "links", "actions", "invariants", "rules", "handoffs", "scenarios"))
            or (len(segs) == 4 and segs[0] == "actions" and segs[2] == "preconditions")
            or (len(segs) == 5 and segs[0] == "transitions" and segs[2] == "matrix"))


def _show(x: Any) -> str:
    return yaml.safe_dump(x, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100)


def _bare(el: Any) -> Any:
    """An element without its provenance, as a person reads it. Provenance sits on the element
    itself and on a matrix cell's per-role parts; a property named `status` or `source` deeper
    inside is the element's content and stays (#207's review)."""
    if not isinstance(el, dict):
        return el
    out = {k: v for k, v in el.items() if k not in ("source", "status")}
    if isinstance(out.get("by_role"), dict):
        out["by_role"] = {r: ({k: v for k, v in part.items() if k not in ("source", "status")}
                              if isinstance(part, dict) else part) for r, part in out["by_role"].items()}
    return out


def _words_pattern(words: str) -> re.Pattern:
    """The words as typed, matched whole: case and spacing ignored, never inside another word."""
    parts = [re.escape(w) for w in words.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def _answer_of(text: str) -> str | None:
    """The owner's answer in an interview line (`question: …`, `answer: …`)."""
    for line in text.splitlines():
        if line.startswith("answer: "):
            return line[len("answer: "):]
    return None


def _get(doc: Any, segs: list[str]) -> Any:
    cur = doc
    for i, s in enumerate(segs):
        if isinstance(cur, list) and segs[i - 1] in LIST_BY_ID:
            cur = next((x for x in cur if isinstance(x, dict) and x.get("id") == s), None)
        elif isinstance(cur, dict):
            cur = cur.get(s)
        else:
            return None
        if cur is None:
            return None
    return cur


def _set(doc: dict, segs: list[str], value: Any) -> None:
    cur: Any = doc
    for i, s in enumerate(segs[:-1]):
        nxt_is_list = s in LIST_BY_ID
        if isinstance(cur, list):
            item = next((x for x in cur if isinstance(x, dict) and x.get("id") == s), None)
            if item is None:
                item = {"id": s}
                cur.append(item)
            cur = item
            continue
        if s not in cur or cur[s] is None:
            cur[s] = [] if nxt_is_list else {}
        cur = cur[s]
    last = segs[-1]
    if isinstance(cur, list) and value is not None and not isinstance(value, dict):
        raise AuthoringError(fixed(f"{'.'.join(segs)}: an item of {segs[-2]} must be an object", "give the item as a mapping, such as `{id: x, check: ...}`"))
    if isinstance(cur, list):
        idx = next((k for k, x in enumerate(cur) if isinstance(x, dict) and x.get("id") == last), None)
        if value is None:
            if idx is not None:
                cur.pop(idx)
        elif idx is None:
            cur.append({**value, "id": last})
        else:
            cur[idx] = {**value, "id": last}
    elif value is None:
        cur.pop(last, None)
    else:
        cur[last] = value


def _demote_enclosing(doc: dict, segs: list[str], source: dict[str, Any]) -> None:
    """A change inside an element (`actions.verify.effects`) changes the element: it is proposed
    again, citing the change's source, so a person confirms it. Otherwise an agent could rewrite
    a confirmed element's parts while it still reads `confirmed`."""
    for k in range(len(segs) - 1, 1, -1):
        if is_element(segs[:k]):
            el = _get(doc, segs[:k])
            if isinstance(el, dict):
                el["status"], el["source"] = "proposed", source
            return


def _no_provenance_path(segs: list[str]) -> None:
    """`source` and `status` are set by the tool, never written directly: otherwise an agent
    could write `actions.X.status: confirmed` (only a person confirms)."""
    if segs[0] != "glossary" and segs[-1] in ("status", "source") and len(segs) > 1 and segs[-2] != "properties":
        raise AuthoringError(fixed(f"{'.'.join(segs)}: provenance is set by the tool; propose the element itself", "propose the element at its own path; the tool records its source and status"))


def _demote(v: Any) -> Any:
    """Agents never write `confirmed`, at any depth (nested preconditions, by_role denies)."""
    if isinstance(v, dict):
        return {k: ("proposed" if k == "status" and x == "confirmed" else _demote(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_demote(x) for x in v]
    return v


class Workspace:
    def __init__(self, root: str | Path):
        """`root` is a workspace directory (with `toprope.workspace.yaml`), or a workspace file
        itself, so that one directory can hold several domains' workspaces (e.g. the two self
        domains reading the same repository)."""
        given = Path(root).resolve()
        if given.is_file():
            self.root, cfg_path = given.parent, given
        else:
            self.root, cfg_path = given, given / CONFIG
        if not cfg_path.exists():
            raise AuthoringError(fixed(f"no {CONFIG} in {self.root}", "check the path given by `--workspace` or by `workspace:` in toprope.yaml; it names a workspace file or its directory"))
        cfg = load_yaml(cfg_path.read_text()) or {}
        self.domain_path = self.root / cfg["domain"]
        self.log_path = self.root / cfg.get("interview_log", "interview/log.jsonl")
        self.usage_path = self.root / cfg.get("usage_log", "interview/sources-used.jsonl")
        self.budget_minutes = cfg.get("budget_minutes")
        es = cfg.get("event_store")
        self.event_store = (f"sqlite:{self.root / es[7:]}" if es and es.startswith("sqlite:") else es)
        self.exclude = tuple(DEFAULT_EXCLUDE) + tuple(cfg.get("exclude", []))
        self.extra = [(r["name"], re.compile(r["pattern"])) for r in cfg.get("redact", [])]
        self.sources: dict[str, SourceSpec] = {}
        for s in cfg.get("sources", []):
            if bool(s.get("url")) == bool(s.get("path")):
                raise AuthoringError(fixed(f"source {s.get('id')!r}: give either a path or a url", "give the source exactly one of `path:` or `url:` in the workspace file"))
            path = s.get("path") or f"{SNAPSHOTS}/{s['id']}"
            spec = SourceSpec(s["id"], s.get("kind", "records"), path, tuple(s.get("globs", [])),
                              bool(s.get("local_only", False)), tuple(s.get("exclude", [])), s.get("url"))
            self.sources[spec.id] = spec
        self._chunks: dict[str, list[Chunk]] = {}

    # -- sources ---------------------------------------------------------------------------
    def chunks(self, source_id: str) -> list[Chunk]:
        spec = self.sources.get(source_id)
        if spec is None:
            raise AuthoringError(fixed(f"no source {source_id!r}", "use a source id listed in the workspace file's `sources:`, or add the source there with a `path:` or `url:`"))
        if spec.kind == "interview-log" or source_id not in self._chunks:
            self._chunks[source_id] = read(spec, self.root, self.extra, self.exclude)
        return self._chunks[source_id]

    def stale_sources(self) -> list[str]:
        """Sources that no longer point at a file (a removed path, a glob matching nothing)."""
        return [m for s in self.sources.values() for m in stale(s, self.root, self.exclude)]

    def list_sources(self) -> list[dict[str, Any]]:
        out = []
        for s in self.sources.values():
            row = {"id": s.id, "kind": s.kind, "path": s.path, "local_only": s.local_only,
                   "chunks": len(self.chunks(s.id))}
            if s.url:
                meta = self.root / s.path / "snapshot.json"
                row.update(url=s.url, fetched=json.loads(meta.read_text()) if meta.exists() else None)
            out.append(row)
        return out

    def fetch(self, source_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch link sources into their snapshots (all, or one). Re-fetching replaces the
        snapshot; refs into it may change, so fetch before drafting from it."""
        if source_id and source_id not in self.sources:
            raise AuthoringError(fixed(f"no source {source_id!r}", "use a source id listed in the workspace file's `sources:`, or add the source there with a `path:` or `url:`"))
        targets = [self.sources[source_id]] if source_id else [s for s in self.sources.values() if s.url]
        out = []
        for spec in targets:
            if not spec.url:
                raise AuthoringError(fixed(f"source {spec.id!r} is a path, not a link", "fetch only a source with a `url:`; a `path:` source is read in place"))
            try:
                out.append({"id": spec.id, **fetch(spec, self.root)})
            except FetchError as e:
                raise AuthoringError(str(e)) from None
            self._chunks.pop(spec.id, None)
        return out

    def read_source(self, source_id: str, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        spec = self.sources.get(source_id)
        if spec is None:
            raise AuthoringError(fixed(f"no source {source_id!r}", "use a source id listed in the workspace file's `sources:`, or add the source there with a `path:` or `url:`"))
        if spec.local_only:
            raise AuthoringError(fixed(f"source {source_id!r} is local-only: its content is never sent to a model", "read it yourself, or remove `local_only: true` from the source if its content may be shared"))
        cs = self.chunks(source_id)[offset:offset + limit]
        self._used(source_id, [c.ref for c in cs])
        return {"source": source_id, "offset": offset, "total": len(self.chunks(source_id)),
                "chunks": [{"ref": c.ref, "text": c.text, "redactions": c.redactions} for c in cs]}

    def search_sources(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        hits = []
        for spec in self.sources.values():
            if spec.local_only:
                continue
            for c in self.chunks(spec.id):
                i = c.text.lower().find(q)
                if i >= 0:
                    hits.append({"ref": c.ref, "snippet": c.text[max(0, i - 120):i + 240]})
                    if len(hits) >= limit:
                        break
            if len(hits) >= limit:
                break
        for sid in {h["ref"].split(":", 1)[0] for h in hits}:
            self._used(sid, [h["ref"] for h in hits if h["ref"].startswith(sid + ":")])
        return hits

    def _used(self, source_id: str, refs: list[str]) -> None:
        self._append(self.usage_path, {"at": _now(), "source": source_id, "refs": refs})

    def resolve_ref(self, ref: str) -> tuple[str, str | None]:
        """A citation as written: an exact chunk ref, or words from the passage (ADR-0049, B4).
        Words resolve to the one chunk that contains them (case and spacing ignored), within the
        source named before a colon if there is one. Returns (ref, the quote, if words were given)."""
        sid, _, rest = ref.partition(":")
        if sid in self.sources and any(c.ref == ref for c in self.chunks(sid)):
            return ref, None
        if len(ref.split()) < 2:                     # one token: meant as a ref, not as words
            if sid not in self.sources or not rest:
                raise AuthoringError(fixed(f"unknown source in ref {ref!r}",
                                           "cite a ref of the form `<source>:<chunk>`, as `search` returns "
                                           "it, or quote words from the passage"))
            raise AuthoringError(fixed(f"no chunk {ref!r}", "run `search` with words from the passage, and "
                                       "cite the `ref` it returns, or quote the words"))
        if sid in self.sources and rest.strip():
            specs, words = [self.sources[sid]], rest
        else:
            specs, words = list(self.sources.values()), ref
        if any(s.local_only for s in specs) and len(specs) == 1:
            # matching would tell a model whether a phrase is in content it may not read (#206's review)
            raise AuthoringError(fixed(f"source {specs[0].id!r} is local-only, so it is not searched for words",
                                       "cite its chunk ref, as the owner gives it"))
        specs = [s for s in specs if not s.local_only]
        words = words.strip().strip('"').strip()
        pattern = _words_pattern(words)
        hits: list[tuple[str, str, str]] = []           # (ref, the passage's own words, source)
        for s in specs:
            for c in self.chunks(s.id):
                # in an interview line only the owner's answer is quoted, never the question asked
                text = (_answer_of(c.text) if s.kind == "interview-log" else c.text) or ""
                if m := pattern.search(text):
                    hits.append((c.ref, m.group(0), s.id))
        if len(hits) > 1:            # the same passage read through several sources: the first declared
            places = {h[0].split(":", 1)[1] for h in hits}
            if len(places) == 1:
                hits = hits[:1]
        if not hits:
            raise AuthoringError(fixed(f"no chunk {ref!r}, and no passage contains those words",
                                       "run `search` with words from the passage, and cite the `ref` it "
                                       "returns or words it shows"))
        if len(hits) > 1:
            shown = ", ".join(h[0] for h in hits[:5]) + (f" and {len(hits) - 5} more" if len(hits) > 5 else "")
            raise AuthoringError(fixed(f"{len(hits)} passages contain {words!r}: {shown}",
                                       "quote more of the passage, or cite one of those refs"))
        ref, said, source = hits[0]
        self._used(source, [ref])
        return ref, " ".join(said.split())             # the passage's own words, not what was typed

    def source_of(self, ref: str, quote: str | None = None) -> dict[str, Any]:
        """Where an element came from: its chunk, and the owner's words if given. A citation by
        quote records the chunk it resolved to, and the quote."""
        ref, quoted = self.resolve_ref(ref)
        spec = self.sources[ref.split(":", 1)[0]]
        out = {"kind": ELEMENT_KIND[spec.kind], "ref": ref}
        if quote or quoted:
            out["quote"] = quote or quoted
        return out

    # -- the draft -------------------------------------------------------------------------
    def draft(self) -> dict[str, Any]:
        if not self.domain_path.exists():
            return {"domain": self.domain_path.name.split(".")[0].replace("-", "_"), "version": 1}
        return load_yaml(self.domain_path.read_text()) or {}

    def _write(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        """Write the draft only if it parses as a declaration; return the validation issues.
        Once the domain has a commit, its working copy is what the generated tools run, and they
        refuse a declaration with errors. So a change that adds an error is refused there, and
        nothing is written: propose what it refers to first (#124)."""
        try:
            d = Domain.model_validate(doc)
        except ValidationError as e:
            raise AuthoringError(fixed(f"the draft would not parse: {e.errors()[0]['loc']}: {e.errors()[0]['msg']}", "fix the element at that location so the declaration matches the schema (docs/domain-schema.md)")) from None
        issues = validate_domain(d)
        if self.domain_path.exists() and self.commits.log(d.domain):
            before = {(i.code, i.where) for i in validate_domain(Domain.model_validate(self.draft()))
                      if i.severity == "error"}
            new = [i for i in issues if i.severity == "error" and (i.code, i.where) not in before]
            if new:
                raise AuthoringError(
                    fixed(f"{d.domain} is committed, and its tools refuse a declaration with errors; this change "
                    "would add " + "; ".join(f"{i.code} at {i.where}: {i.message}" for i in new) +
                    ". Propose what it refers to first.", "propose the elements it refers to first, then this one"))
        self.domain_path.parent.mkdir(parents=True, exist_ok=True)
        self.domain_path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
        return [{"code": i.code, "where": i.where, "message": i.message, "severity": i.severity}
                for i in issues]

    def _with_provenance(self, segs: list[str], value: Any, source: dict[str, Any]) -> Any:
        if segs[0] != "glossary":
            value = _demote(copy.deepcopy(value))
        if value is None or not is_element(segs):
            return value
        if isinstance(value, str) and segs[0] == "transitions":
            if value in ("n/a", UNDECIDED):
                return value            # a bare cell carries no provenance in schema v1
            value = {"to": value}
        if not isinstance(value, dict):
            raise AuthoringError(fixed(f"{'.'.join(segs)} must be an object", "give the value as a mapping"))
        return {**value, "source": source, "status": "proposed"}

    def propose(self, path: str, value: Any, source_ref: str, quote: str | None = None) -> dict[str, Any]:
        segs = element_path(path)
        _no_provenance_path(segs)
        src = self.source_of(source_ref, quote)
        doc = self.draft()
        _set(doc, segs, self._with_provenance(segs, value, src))
        _demote_enclosing(doc, segs, src)
        issues = self._write(doc)
        marked = is_element(segs) or any(is_element(segs[:k]) for k in range(2, len(segs)))
        if not marked:
            # Fixtures and the glossary carry no provenance: the change is logged, so the person
            # sees it with what is to confirm, and it shows in the commit's review diff.
            self._append(self.log_path, {"at": _now(), "kind": "unmarked-proposal", "path": path,
                                         "source": src.get("ref")})
        return {"path": path, "status": "proposed", "marked": marked, "issues": issues}

    def answer(self, question_id: str, answer: str, decisions: list[dict[str, Any]],
               question: str | None = None) -> dict[str, Any]:
        """Record the owner's answer (their words) and apply its decisions as proposed
        elements citing the answer. Confirmation is a separate, human-only step."""
        if not answer.strip():
            raise AuthoringError(fixed("an answer quotes the owner's words", "pass the owner's answer, in their words, as the answer text"))
        text = question or self._all_questions().get(question_id)
        if text is None:
            raise AuthoringError(fixed(f"unknown question {question_id!r}: pass its text", "pass the question's text with the answer, or use an id `next_questions` returned"))
        doc = self.draft()
        n = self._lines(self.log_path) + 1
        ref = f"{self._log_source_id()}:{self.log_path.relative_to(self.root).as_posix()}#L{n}"
        for dec in decisions:
            segs = element_path(dec["path"])
            _no_provenance_path(segs)
            src = {"kind": "interview", "ref": ref, "quote": answer}
            _set(doc, segs, self._with_provenance(segs, dec.get("value"), src))
            _demote_enclosing(doc, segs, src)
        issues = self._write(doc) if decisions else []
        stage = question_id.split(":")[1] if question_id.startswith("bundle:") else self._current_stage()
        self._append(self.log_path, {"at": _now(), "kind": "answer", "stage": stage, "question_id": question_id,
                                     "question": text, "answer": answer,
                                     "decisions": [d["path"] for d in decisions]})
        return {"ref": ref, "applied": [d["path"] for d in decisions], "issues": issues}

    def _log_source_id(self) -> str:
        rel = self.log_path.relative_to(self.root).as_posix()
        return next((s.id for s in self.sources.values() if s.kind == "interview-log"
                     and (s.path == rel or rel.startswith(s.path.rstrip("/") + "/"))), "interview")

    def identity(self) -> str | None:
        """Who is at this terminal, named as the git identity adapter names them: `name <email>`
        from the identity file when it lists this repository's git email, else git's
        `user.name <user.email>`, else the login name. Recorded with confirmations and approvals
        made at the terminal, so the log says who decided without anyone typing it."""
        import getpass
        import subprocess

        from ..identity.git import FILE, git_email, load_table
        table = self.root / FILE
        email = git_email(self.root)
        if email and table.exists():
            try:
                listed = load_table(table).get(email)
            except ValueError:
                listed = None
            if listed is not None:
                return listed.actor.id

        def git(key: str) -> str:
            try:
                out = subprocess.run(["git", "-C", str(self.root), "config", key], capture_output=True,
                                     text=True, timeout=5, check=False)
                return out.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                return ""
        name, email = git("user.name"), git("user.email")
        if name:
            return f"{name} <{email}>" if email else name
        try:
            return getpass.getuser() or None
        except Exception:  # noqa: BLE001 - no login name: record nothing rather than guess
            return None

    def confirm(self, paths: list[str], via: str, who: str | None = None) -> dict[str, Any]:
        """Mark elements confirmed. Only a person confirms: through a declared action the kernel
        checked was taken by that person (`kernel`, naming them), or at their own terminal
        (`terminal`, where `who` defaults to the terminal's identity)."""
        if via not in CHANNELS:
            raise AuthoringError(fixed("only a person confirms: at their own terminal, or through a declared action the "
                                 "kernel checked was taken by that person", "ask the person to run the confirm action themselves, at their terminal or through a human request"))
        if via == "kernel" and not who:
            raise AuthoringError(fixed("a confirmation through the kernel names the person who took it", "pass the person who confirmed, as the kernel recorded them"))
        if who is None and via == "terminal":
            who = self.identity()
        doc = self.draft()
        for p in paths:
            segs = element_path(p)
            el = _get(doc, segs)
            if not is_element(segs) or not isinstance(el, dict) or "source" not in el:
                raise AuthoringError(fixed(f"{p} is not a drafted element with a source", "confirm only elements that were proposed with a source; `next_questions` lists them"))
            el["status"] = "confirmed"
            for part in (el.get("by_role") or {}).values():   # a cell's per-role parts are one element
                if isinstance(part, dict) and part.get("status") == "proposed":
                    part["status"] = "confirmed"
        issues = self._write(doc)
        self._append(self.log_path, {"at": _now(), "kind": "confirm", "paths": paths, "via": via, "who": who})
        return {"confirmed": paths, "issues": issues}

    # -- one diff to confirm (ADR-0049, B5) ---------------------------------------------------
    def review(self) -> list[dict[str, Any]]:
        """Every element still proposed in the working copy: what it says now, what the domain's
        approved `main` says there (None: new), and where it came from. A person confirms from this
        one view instead of reading the draft element by element."""
        doc = self.draft()
        before: dict[str, Any] = {}
        d = doc.get("domain")
        main = self.commits.main(d) if isinstance(d, str) and d and self.commits.log(d) else None
        if main is not None:
            before = self.commits.declaration(d, main.id)
        out = []
        for path in self._proposed(doc):
            segs = element_path(path)
            el = _get(doc, segs)
            old = _get(before, segs) if before else None
            out.append({"path": path, "now": _bare(el), "before": _bare(old) if old is not None else None,
                        "source": (el or {}).get("source") if isinstance(el, dict) else None,
                        "main": main.id if main else None})
        return out

    def render_review(self) -> str:
        items = self.review()
        if not items:
            return "Nothing is proposed: there is nothing to confirm.\n"
        lines = [f"{len(items)} proposed element(s), against main "
                 f"{items[0]['main'] or '(none yet: every element is new)'}:", ""]
        for it in items:
            src = it["source"] or {}
            lines.append(f"{'~' if it['before'] is not None else '+'} {it['path']}"
                         f"    (from {src.get('ref', '?')})")
            if src.get("quote"):
                lines.append(f'    "{src["quote"]}"')
            if it["before"] is not None:
                for ln in _show(it["before"]).rstrip().splitlines():
                    lines.append(f"    - {ln}")
            for ln in _show(it["now"]).rstrip().splitlines():
                lines.append(f"    + {ln}")
            lines.append("")
        return "\n".join(lines)

    # -- interview questions (ADR-0014) ----------------------------------------------------
    def attempts_by_action(self) -> dict[str, int]:
        """Attempts that hit an undecided cell, per action, from the configured event store
        (`event_store` in the workspace config). M0a attributes them to the action, because
        attempt events do not record the state they were made in."""
        if not self.event_store:
            return {}
        from ..store import open_store
        try:
            store = open_store(self.event_store)
        except ValueError as e:
            raise AuthoringError(fixed(f"event_store: {e}", "set `event_store:` in the workspace file to `sqlite:FILE`, `jsonl:DIR` or `memory`")) from None
        out: dict[str, int] = {}
        for stream in store.streams():
            for e in store.read_attempts(stream):
                if e.payload.get("code") == UNDECIDED:
                    out[e.payload["action"]] = out.get(e.payload["action"], 0) + 1
        return out

    def _plan(self, attempts: dict[str, int] | None = None):
        from .stages import Plan
        doc = self.draft()
        try:
            d = Domain.model_validate(doc)
            issues = validate_domain(d)
        except ValidationError:
            d, issues = None, []
        return Plan(self, doc, d, issues, attempts if attempts is not None else self.attempts_by_action())

    def questions(self, limit: int = 10, attempts: dict[str, int] | None = None,
                  stage: str | None = None) -> dict[str, Any]:
        """The bundle of questions for the current stage (or `stage`), with progress (ADR-0025).
        Answer the whole bundle at once with `answer(bundle_id, ...)`."""
        from .stages import BY_NAME
        plan = self._plan(attempts)
        if plan.d is None:   # _plan found the draft does not parse; say why
            try:
                Domain.model_validate(plan.doc)
            except ValidationError as e:
                why = f"the draft does not parse: {e.errors()[0]['msg']}"
            return {"stage": None, "questions": [], "progress": [], "stop": {"stop": False, "why": why}}
        if stage is not None and stage not in BY_NAME:
            raise AuthoringError(fixed(f"unknown stage {stage!r}: one of {list(BY_NAME)}", "use one of the stages listed"))
        st = BY_NAME[stage] if stage else plan.current()
        if st is None:
            return {"stage": None, "goal": "Every stage is done.", "questions": [], "total": 0,
                    "progress": plan.progress(), "stop": self._stop(plan.d, plan.attempts)}
        qs = plan.bundle(st)
        return {"stage": st.name, "title": st.title, "goal": st.goal, "optional": st.optional,
                "bundle_id": self._bundle_id(st.name, qs),
                "questions": [x.as_dict() for x in qs[:limit]], "total": len(qs),
                "progress": plan.progress(), "stop": self._stop(plan.d, plan.attempts)}

    @staticmethod
    def _bundle_id(stage: str, qs) -> str:
        return f"bundle:{stage}:" + hashlib.sha1("|".join(q.id for q in qs).encode()).hexdigest()[:8]

    def _all_questions(self) -> dict[str, str]:
        """Every question of every stage, and each stage's bundle, by id → text."""
        from .stages import STAGES
        plan = self._plan()
        out: dict[str, str] = {}
        if plan.d is None:
            return out
        for st in STAGES:
            qs = plan.bundle(st)
            for q in qs:
                out[q.id] = q.text
            out[self._bundle_id(st.name, qs)] = f"[{st.title}] " + " / ".join(q.text for q in qs)
        return out

    def _current_stage(self) -> str | None:
        plan = self._plan({})
        cur = plan.current() if plan.d is not None else None
        return cur.name if cur else None

    def progress(self) -> dict[str, Any]:
        plan = self._plan()
        cur = plan.current() if plan.d is not None else None
        return {"current": cur.name if cur else None, "stages": plan.progress(),
                "proposed": len(self._proposed(plan.doc))}

    def skip_stage(self, stage: str, reason: str) -> dict[str, Any]:
        """The owner says an optional stage has nothing (e.g. no invariants, no handoffs).
        Recorded in their words in the interview log."""
        from .stages import BY_NAME
        st = BY_NAME.get(stage)
        if st is None or not st.optional:
            raise AuthoringError(fixed(f"only optional stages can be skipped: "
                                 f"{[s for s, x in BY_NAME.items() if x.optional]}", "skip only an optional stage listed; answer the others"))
        if not reason.strip():
            raise AuthoringError(fixed("a skip quotes the owner's reason", "pass the owner's reason for skipping, in their words"))
        self._append(self.log_path, {"at": _now(), "kind": "skip", "stage": stage, "reason": reason})
        return self.progress()

    def _cell_questions(self, d: Domain, attempts: dict[str, int]) -> list[Question]:
        """ADR-0014 within the transitions stage: defaults first, then grouped rows, by priority."""
        qs: list[Question] = []

        def q(kind: str, subject: str, text: str, decides: list[str], priority: float) -> None:
            qid = hashlib.sha1(f"{kind}:{subject}".encode()).hexdigest()[:10]
            qs.append(Question(qid, kind, text, decides, priority))

        for obj, tr in d.transitions.items():
            acts = {n: a for n, a in d.actions.items() if a.target == obj and a.creates is None}
            # Defaults first: one question settles an action's whole column.
            for name, a in acts.items():
                undecided = [s for s in tr.matrix if tr.matrix[s].get(name, UNDECIDED) == UNDECIDED]
                if len(undecided) >= 2 and a.applies_in is None:
                    q("default", f"{obj}.{name}", f"In which states can someone '{a.description.rstrip('.').lower()}' "
                      f"at all? Everywhere else it will be not applicable.",
                      [f"transitions.{obj}.matrix.{s}.{name}" for s in undecided],
                      self._priority(undecided, a, attempts.get(name, 0)))
            # Then grouped rows: one question per state with undecided cells.
            for state, cells in tr.matrix.items():
                undecided = [n for n in acts if cells.get(n, UNDECIDED) == UNDECIDED]
                if not undecided:
                    continue
                names = ", ".join(acts[n].description.rstrip(".").lower() for n in undecided)
                q("row", f"{obj}.{state}", f"Once a {obj} is {state}, can anyone still: {names}? "
                  "If so, who, and what does it become?",
                  [f"transitions.{obj}.matrix.{state}.{n}" for n in undecided],
                  max(self._priority([state], acts[n], attempts.get(n, 0)) for n in undecided) + len(undecided))
        return qs

    @staticmethod
    def _priority(cells: list[str], a, attempts: int) -> float:
        risk = 1 if (a.effects or a.records_decision) else 0
        return attempts * 100 + risk * 10 + len(cells)

    def _proposed(self, doc: dict[str, Any]) -> list[str]:
        from ..decl.provenance import proposed_elements
        return proposed_elements(doc)

    def _stop(self, d: Domain, attempts: dict[str, int]) -> dict[str, Any]:
        """ADR-0014 §4: stop when no attempted (or effectful) cell is undecided, or the budget
        is spent. Undecided cells deny by default and stay listed."""
        open_cells = []
        for obj, tr in d.transitions.items():
            for name, a in d.actions.items():
                if a.target != obj or a.creates is not None:
                    continue
                if not (attempts.get(name) or a.effects):
                    continue
                open_cells += [f"{obj}.{s}.{name}" for s in tr.matrix if tr.matrix[s].get(name, UNDECIDED) == UNDECIDED]
        spent = None
        log = self._read(self.log_path)
        if self.budget_minutes and log:
            started = datetime.fromisoformat(log[0]["at"])
            spent = (datetime.now(timezone.utc) - started).total_seconds() / 60 >= self.budget_minutes
        if spent:
            return {"stop": True, "why": "the time budget is spent", "open": open_cells}
        if not open_cells:
            return {"stop": True, "why": "every attempted or effectful cell is decided", "open": []}
        return {"stop": False, "why": f"{len(open_cells)} attempted or effectful cells are undecided", "open": open_cells}

    # -- commits (ADR-0029; bootstrap until the generated Authoring tool takes over) ---------
    @property
    def commits(self):
        from ..commits import CommitStore
        return CommitStore(self.root / ".toprope" / "commits")

    def commit(self, message: str = "", branch: str = "work", merge: str | None = None,
               author: str = "") -> dict[str, Any]:
        """Compile the working copy into an immutable commit on a branch (ADR-0033). Returns what
        to re-confirm: the elements that changed directly since the branch's merge base with
        `main` (`since`; None before the first approval). `merge` names the commit whose
        conflicts this working copy resolves."""
        from ..commits import CommitError
        try:
            c, created = self.commits.commit(self.domain_path, message=message, branch=branch, merge=merge,
                                             author=author)
        except ValidationError as e:
            raise AuthoringError(fixed(f"the draft does not parse: {e.errors()[0]['msg']}", "fix the draft so it matches the schema (docs/domain-schema.md), then commit again")) from None
        except CommitError as e:
            raise AuthoringError(str(e)) from None
        base_id = self.commits.review_base(c.domain, c.id)   # ADR-0033
        review = self.commits.diff(c.domain, base_id, c.id)
        return {"commit": c.id, "seq": c.seq, "branch": branch, "created": created, "interface": c.interface,
                "since": base_id, **review}

    def change_check(self, commit_id: str | None = None, branch: str = "work", since: str | None = None,
                     env: str | Path | None = None, examples: int = 50, cache: bool = True,
                     full: bool = False) -> dict[str, Any]:
        """Run the change check on a commit (default: the branch head) and record it on the
        commit (ADR-0009, ADR-0032). `since` is the base (default: the merge base with `main`);
        `env` a deploy environment, whose event store feeds log replay and the in-flight check.
        The report is also written to `.toprope/checks/<commit>.json`. Unchanged tests come
        from the result cache in `.toprope/cache` (ADR-0013) unless `cache` is False; `full`
        also runs everything uncached and lists selection misses (target 0)."""
        from ..check import check_commit
        from ..commits import CommitError
        d = self.draft().get("domain")
        if not isinstance(d, str) or not d:
            raise AuthoringError(fixed("the draft names no `domain`, so there is no commit log to check", "set `domain:` at the top of the draft"))
        try:
            if commit_id is None:
                refs = self.commits.refs(d)
                if not refs:
                    raise AuthoringError(fixed("nothing to check: commit first", "run `commit_draft` first, then check the commit it makes"))
                if branch not in refs:
                    raise AuthoringError(fixed(f"no branch {branch!r}; branches: {sorted(refs)}", "use one of the branches listed"))
                commit_id = refs[branch]
            base = since if since is not None else "merge-base"
            from ..incremental import ResultCache
            if full and not cache:
                raise AuthoringError(fixed("--full compares with the result cache; it cannot run with --no-cache", "drop `--no-cache`, or drop `--full`"))
            rc = ResultCache(self.root / ".toprope" / "cache") if cache else None
            if env is not None:
                from ..deploy import LocalEnvironment
                if not Path(env).is_dir():
                    raise AuthoringError(fixed(f"no deploy environment at {env}", "pass `--env` the directory of a local deploy environment, or set `env:` in toprope.yaml"))
                with LocalEnvironment(env).events(d) as store:
                    report = check_commit(self.commits, d, commit_id, base, events=store, examples=examples,
                                          cache=rc, full=full)
            else:
                report = check_commit(self.commits, d, commit_id, base, examples=examples, cache=rc, full=full)
        except CommitError as e:
            raise AuthoringError(str(e)) from None
        out = {"commit": commit_id, **report.to_json()}
        path = self.root / ".toprope" / "checks" / f"{commit_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return out

    def checkout(self, commit_id: str, force: bool = False) -> dict[str, Any]:
        """Load a commit into the working copy (ADR-0032); committing it is a revert or a restart.
        Refused when the working copy has changes no commit holds, unless `force`."""
        from ..commits import CommitError
        try:
            d = self.draft().get("domain")
        except Exception as e:                       # noqa: BLE001 - an unreadable draft
            if not force:
                raise AuthoringError(fixed(f"cannot read the working copy: {e}", "fix the declaration file so it parses, or restore it with `git checkout -- <file>`, then check out again")) from None
            d = next((x.name for x in sorted(self.commits.root.glob("*")) if x.is_dir()
                      and any(c.id == commit_id for c in self.commits.log(x.name))), None)
        if not isinstance(d, str) or not d:
            raise AuthoringError(fixed("the draft names no `domain`, so there is no commit log to check out from", "set `domain:` at the top of the draft"))
        try:
            c = self.commits.checkout(d, commit_id, self.domain_path, force=force)
        except CommitError as e:
            raise AuthoringError(str(e)) from None
        return {"commit": c.id, "content": c.content}

    def element_log(self, key: str, at: str | None = None) -> list[dict[str, Any]]:
        """An element's history (ADR-0032): the commits that changed it, with what it cites."""
        from ..commits import CommitError
        d = self.draft().get("domain")
        if not isinstance(d, str) or not d:
            raise AuthoringError(fixed("the draft names no `domain`, so there is no commit log", "set `domain:` at the top of the draft"))
        try:
            return self.commits.element_log(d, key, at)
        except CommitError as e:
            raise AuthoringError(str(e)) from None

    def merge_main(self, branch: str = "work") -> dict[str, Any]:
        """Bring `main` into a branch's working copy (ADR-0033). Writes the semantic 3-way merge
        into the working copy and lists the conflicts for the person to resolve: at a path
        conflict the branch's value is kept; at an element conflict the element holds both
        sides' changes, field by field, for the person to judge. Then `commit(merge=<main>)` records both parents.
        Refuses when the working copy has changes not yet committed to the branch."""
        d = self.draft().get("domain")
        if not isinstance(d, str) or not d:
            raise AuthoringError(fixed("the draft names no `domain`, so there is no commit log to merge in", "set `domain:` at the top of the draft"))
        from ..commits import CommitError
        try:
            return self.commits.merge_main(d, self.domain_path, branch, self.draft().get("version", 1))
        except CommitError as e:
            raise AuthoringError(str(e)) from None

    def approve_commit(self, commit_id: str, via: str, who: str) -> dict[str, Any]:
        """Approve a commit: merge it into `main` and tag the result (ADR-0033). Only a person,
        through a human channel (as `confirm`). Conflicts are an error that lists them; bring
        `main` into the branch with `merge_main`, resolve, commit, and approve again."""
        if via not in CHANNELS:
            raise AuthoringError(fixed("only a person approves: at their own terminal, or through a declared action", "ask the person to run `approve_commit` themselves, at their terminal or through a human request"))
        d = self.draft().get("domain")
        if not isinstance(d, str) or not d:
            raise AuthoringError(fixed("the draft names no `domain`, so there is no commit log to approve in", "set `domain:` at the top of the draft"))
        from ..commits import CommitError
        try:
            target = self.commits.approve(d, commit_id, who)
        except CommitError as e:
            raise AuthoringError(str(e)) from None
        main = self.commits.main(d)
        self._append(self.log_path, {"at": _now(), "kind": "approve", "commit": commit_id, "main": main.id if main else None,
                                     "via": via, "who": who})
        return {"commit": commit_id, "approved": True, "new": target is not None, "main": main.id if main else None}

    # -- logs ------------------------------------------------------------------------------
    def _append(self, path: Path, entry: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _lines(path: Path) -> int:
        return sum(1 for _ in path.open()) if path.exists() else 0

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []

    def check(self, levels: tuple[str, ...] = ("model",), examples: int = 50) -> dict[str, Any]:
        """Validate the draft, run the harness on it, and summarize the world map."""
        doc = self.draft()
        try:
            d = Domain.model_validate(doc)
        except ValidationError as e:
            return {"parses": False, "error": str(e.errors()[0])}
        issues = validate_domain(d)
        out: dict[str, Any] = {"parses": True, "issues": [{"code": i.code, "where": i.where, "message": i.message,
                                                           "severity": i.severity} for i in issues]}
        if any(i.severity == "error" for i in issues):
            return out
        from ..harness import run_harness
        from ..worldmap import build_world_map
        r = run_harness(d, levels=levels, explore_examples=examples, races=False)
        wm = build_world_map(d, r.to_json())
        edges = wm["behavior"]["edges"]
        out["harness"] = {"ok": r.ok, "summary": r.summary()}
        out["matrix"] = {"cells": len(edges), "undecided": sum(e["fog"] for e in edges),
                         "proposed": len(self._proposed(doc))}
        return out


__all__ = ["CONFIG", "AuthoringError", "Question", "Workspace"]
