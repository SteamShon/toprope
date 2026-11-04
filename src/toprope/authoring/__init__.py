"""The authoring workspace (ADR-0014, ADR-0017): draft a declaration from sources, interview
its owner, and confirm.

Rules it enforces:
- every drafted element cites a real source chunk (`source.ref`), so no rule is unsupported
- agents write only `proposed`: `propose` and `answer` never set `confirmed`
- only a person confirms: `confirm` is called with the channel the confirmation came
  through (the CLI on the owner's terminal, or an MCP elicitation shown to the user), and
  each confirmation is logged with that channel
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
from ..sources import DEFAULT_EXCLUDE, ELEMENT_KIND, SNAPSHOTS, Chunk, FetchError, SourceSpec, fetch, read

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def element_path(path: str) -> list[str]:
    segs = path.split(".")
    if not path or any(not s for s in segs):
        raise AuthoringError(f"bad element path {path!r}")
    return segs


def is_element(segs: list[str]) -> bool:
    """Paths whose value carries `source` and `status` (Provenance in decl/models.py)."""
    return ((len(segs) == 2 and segs[0] in ("objects", "links", "actions", "invariants"))
            or (len(segs) == 4 and segs[0] == "actions" and segs[2] == "preconditions")
            or (len(segs) == 5 and segs[0] == "transitions" and segs[2] == "matrix"))


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
        raise AuthoringError(f"{'.'.join(segs)}: an item of {segs[-2]} must be an object")
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


def _demote(v: Any) -> Any:
    """Agents never write `confirmed`, at any depth (nested preconditions, by_role denies)."""
    if isinstance(v, dict):
        return {k: ("proposed" if k == "status" and x == "confirmed" else _demote(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_demote(x) for x in v]
    return v


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        cfg_path = self.root / CONFIG
        if not cfg_path.exists():
            raise AuthoringError(f"no {CONFIG} in {self.root}")
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
                raise AuthoringError(f"source {s.get('id')!r}: give either a path or a url")
            path = s.get("path") or f"{SNAPSHOTS}/{s['id']}"
            spec = SourceSpec(s["id"], s.get("kind", "records"), path, tuple(s.get("globs", [])),
                              bool(s.get("local_only", False)), tuple(s.get("exclude", [])), s.get("url"))
            self.sources[spec.id] = spec
        self._chunks: dict[str, list[Chunk]] = {}

    # -- sources ---------------------------------------------------------------------------
    def chunks(self, source_id: str) -> list[Chunk]:
        spec = self.sources.get(source_id)
        if spec is None:
            raise AuthoringError(f"no source {source_id!r}")
        if spec.kind == "interview-log" or source_id not in self._chunks:
            self._chunks[source_id] = read(spec, self.root, self.extra, self.exclude)
        return self._chunks[source_id]

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
            raise AuthoringError(f"no source {source_id!r}")
        targets = [self.sources[source_id]] if source_id else [s for s in self.sources.values() if s.url]
        out = []
        for spec in targets:
            if not spec.url:
                raise AuthoringError(f"source {spec.id!r} is a path, not a link")
            try:
                out.append({"id": spec.id, **fetch(spec, self.root)})
            except FetchError as e:
                raise AuthoringError(str(e)) from None
            self._chunks.pop(spec.id, None)
        return out

    def read_source(self, source_id: str, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        spec = self.sources.get(source_id)
        if spec is None:
            raise AuthoringError(f"no source {source_id!r}")
        if spec.local_only:
            raise AuthoringError(f"source {source_id!r} is local-only: its content is never sent to a model")
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

    def source_of(self, ref: str, quote: str | None = None) -> dict[str, Any]:
        sid = ref.split(":", 1)[0]
        spec = self.sources.get(sid)
        if spec is None:
            raise AuthoringError(f"unknown source in ref {ref!r}")
        if not any(c.ref == ref for c in self.chunks(sid)):
            raise AuthoringError(f"no chunk {ref!r}: cite a ref returned by read_source or search_sources")
        out = {"kind": ELEMENT_KIND[spec.kind], "ref": ref}
        if quote:
            out["quote"] = quote
        return out

    # -- the draft -------------------------------------------------------------------------
    def draft(self) -> dict[str, Any]:
        if not self.domain_path.exists():
            return {"domain": self.domain_path.name.split(".")[0].replace("-", "_"), "version": 1}
        return load_yaml(self.domain_path.read_text()) or {}

    def _write(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        """Write the draft only if it parses as a declaration; return the validation issues."""
        try:
            d = Domain.model_validate(doc)
        except ValidationError as e:
            raise AuthoringError(f"the draft would not parse: {e.errors()[0]['loc']}: {e.errors()[0]['msg']}") from None
        self.domain_path.parent.mkdir(parents=True, exist_ok=True)
        self.domain_path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
        return [{"code": i.code, "where": i.where, "message": i.message, "severity": i.severity}
                for i in validate_domain(d)]

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
            raise AuthoringError(f"{'.'.join(segs)} must be an object")
        return {**value, "source": source, "status": "proposed"}

    def propose(self, path: str, value: Any, source_ref: str, quote: str | None = None) -> dict[str, Any]:
        segs = element_path(path)
        src = self.source_of(source_ref, quote)
        doc = self.draft()
        _set(doc, segs, self._with_provenance(segs, value, src))
        issues = self._write(doc)
        return {"path": path, "status": "proposed", "issues": issues}

    def answer(self, question_id: str, answer: str, decisions: list[dict[str, Any]],
               question: str | None = None) -> dict[str, Any]:
        """Record the owner's answer (their words) and apply its decisions as proposed
        elements citing the answer. Confirmation is a separate, human-only step."""
        if not answer.strip():
            raise AuthoringError("an answer quotes the owner's words")
        text = question or self._all_questions().get(question_id)
        if text is None:
            raise AuthoringError(f"unknown question {question_id!r}: pass its text")
        doc = self.draft()
        n = self._lines(self.log_path) + 1
        ref = f"{self._log_source_id()}:{self.log_path.relative_to(self.root).as_posix()}#L{n}"
        for dec in decisions:
            segs = element_path(dec["path"])
            src = {"kind": "interview", "ref": ref, "quote": answer}
            _set(doc, segs, self._with_provenance(segs, dec.get("value"), src))
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

    def confirm(self, paths: list[str], via: str, who: str | None = None) -> dict[str, Any]:
        """Mark elements confirmed. Call only with a human channel (`cli`, `elicitation`)."""
        if via not in ("cli", "elicitation"):
            raise AuthoringError("only a person confirms, through the CLI or an MCP elicitation")
        doc = self.draft()
        for p in paths:
            segs = element_path(p)
            el = _get(doc, segs)
            if not is_element(segs) or not isinstance(el, dict) or "source" not in el:
                raise AuthoringError(f"{p} is not a drafted element with a source")
            el["status"] = "confirmed"
        issues = self._write(doc)
        self._append(self.log_path, {"at": _now(), "kind": "confirm", "paths": paths, "via": via, "who": who})
        return {"confirmed": paths, "issues": issues}

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
            raise AuthoringError(f"event_store: {e}") from None
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
            raise AuthoringError(f"unknown stage {stage!r}: one of {list(BY_NAME)}")
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
            raise AuthoringError(f"only optional stages can be skipped: "
                                 f"{[s for s, x in BY_NAME.items() if x.optional]}")
        if not reason.strip():
            raise AuthoringError("a skip quotes the owner's reason")
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
        out = []
        for kind in ("objects", "links", "actions"):
            for name, el in (doc.get(kind) or {}).items():
                if isinstance(el, dict) and el.get("status") == "proposed":
                    out.append(f"{kind}.{name}")
                if kind == "actions" and isinstance(el, dict):
                    for p in el.get("preconditions") or []:
                        if isinstance(p, dict) and p.get("status") == "proposed":
                            out.append(f"actions.{name}.preconditions.{p.get('id')}")
        for inv in doc.get("invariants") or []:
            if isinstance(inv, dict) and inv.get("status") == "proposed":
                out.append(f"invariants.{inv.get('id')}")
        for obj, tr in (doc.get("transitions") or {}).items():
            for state, cells in ((tr or {}).get("matrix") or {}).items():
                for name, c in (cells or {}).items():
                    if isinstance(c, dict) and c.get("status") == "proposed":
                        out.append(f"transitions.{obj}.matrix.{state}.{name}")
        return out

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


__all__ = ["AuthoringError", "CONFIG", "Question", "Workspace"]
