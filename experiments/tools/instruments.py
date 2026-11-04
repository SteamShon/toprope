"""Validate, freeze and verify experiment instruments.

Usage (from the repo root):
  uv run --with pyyaml python experiments/tools/instruments.py validate experiments/m1/instruments
  uv run --with pyyaml python experiments/tools/instruments.py freeze   experiments/m1/instruments
  uv run --with pyyaml python experiments/tools/instruments.py freeze-binding experiments/m1/instruments
  uv run --with pyyaml python experiments/tools/instruments.py verify   experiments/m1/instruments [--run]

validate        checks the filled files (not *.template.yaml) for format and cross-file consistency.
freeze          stage 1, researcher only, in M0a before the checks are built: freezes the five
                pre-check instruments (status must be `frozen`) into FROZEN.json. The binding is
                ignored at this stage.
freeze-binding  stage 2, researcher only, after Phase A and before any arm runs: freezes
                binding.yaml. Requires stage 1.
--sealed        with validate: print nothing derived from change-key.yaml beyond errors
                (use it whenever an agent runs the validator for you).
verify          fails if a frozen file changed. It also fails unless all five stage-1 files are
                frozen, and with --run (used by the harness before every arm run) unless the
                binding is frozen too.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

FILES = {
    "gold-scenarios": "gold-scenarios.yaml",
    "probe-suite": "probe-suite.yaml",
    "change-requests": "change-requests.yaml",
    "change-key": "change-key.yaml",
    "binding": "binding.yaml",          # written after Phase A
    "verdict-rules": "verdict-rules.yaml",
}
SEALED = "--sealed" in sys.argv   # validate without printing anything derived from the sealed key
BEFORE_CHECKS = ["gold-scenarios", "probe-suite", "change-requests", "change-key", "verdict-rules"]
ANSWER_KINDS = {"yes_no", "outcome", "state", "actors", "free_text"}
PROBLEMS = {"none", "conflict", "breakage"}
TYPES = {"conflicts-with-rule", "breaks-reference", "breaks-scenario", "breaks-past-behavior",
         "strands-objects"}


def load(d: Path, key: str):
    p = d / FILES[key]
    if not p.exists():
        return None
    try:
        doc = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        return {"__invalid__": f"YAML error: {str(e).splitlines()[0]}"}
    return doc if isinstance(doc, dict) else {"__invalid__": "top level must be a mapping"}


def items(doc, key: str) -> list[dict]:
    v = (doc or {}).get(key) or []
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def validate(d: Path, include_binding: bool = True) -> list[str]:
    errs: list[str] = []
    warn: list[str] = []
    docs = {k: load(d, k) for k in FILES}
    if not include_binding:
        docs["binding"] = None
    for k in FILES:
        if docs[k] is None:
            if k in BEFORE_CHECKS:
                errs.append(f"missing {FILES[k]}")
        elif docs[k].get("__invalid__"):
            errs.append(f"{FILES[k]}: {docs[k]['__invalid__']}")
        elif docs[k].get("instrument") != k:
            errs.append(f"{FILES[k]}: instrument must be '{k}'")
    for k, key in (("change-requests", "requests"), ("change-key", "entries"), ("binding", "bindings")):
        for i, x in enumerate(items(docs[k], key)):
            if not isinstance(x.get("seq"), int):
                errs.append(f"{FILES[k]} entry {i}: seq must be an integer")
    if errs:
        return errs
    if g := docs["gold-scenarios"]:
        ids = [s.get("id") for s in items(g, "scenarios")]
        bad_ids = [i for i in ids if not isinstance(i, str)]
        if bad_ids:
            errs.append(f"gold: ids must be strings, got {bad_ids}")
        elif len(ids) != len(set(ids)):
            errs.append("gold-scenarios: duplicate ids")
        for s in items(g, "scenarios"):
            if not s.get("id"):
                errs.append("gold: every scenario needs an id")
            ans = s.get("answer")
            if not isinstance(ans, dict) or ans.get("kind") not in ANSWER_KINDS:
                errs.append(f"gold {s.get('id')}: answer.kind must be one of {sorted(ANSWER_KINDS)}")
            if "<" in str(s.get("question", "")):
                errs.append(f"gold {s.get('id')}: question still a placeholder")
        held = sum(1 for s in items(g, "scenarios") if s.get("held_out"))
        n = len(ids)
        if n and not (0.35 <= held / n <= 0.65):
            warn.append(f"gold: {held}/{n} held out (target about half)")
    if (r := docs["change-requests"]) and (k := docs["change-key"]):
        seqs = [x["seq"] for x in items(r, "requests")]
        kseqs = [x["seq"] for x in items(k, "entries")]
        if seqs != sorted(seqs) or len(seqs) != len(set(seqs)):
            errs.append("change-requests: seq must be unique and increasing")
        if sorted(seqs) != sorted(kseqs):
            errs.append("change-key: must have exactly one entry per change-request seq")
        for e in items(k, "entries"):
            if e.get("problem") not in PROBLEMS:
                errs.append(f"key seq {e.get('seq')}: problem must be one of {sorted(PROBLEMS)}")
            t = str(e.get("type", ""))
            if e.get("problem") != "none" and not (t in TYPES or t.startswith("other:")):
                errs.append(f"key seq {e.get('seq')}: type must be one of {sorted(TYPES)} or other:<text>")
        counts = {p: sum(1 for e in items(k, "entries") if e.get("problem") == p) for p in PROBLEMS}
        if not SEALED:   # the key mix is part of the sealed key: never printed for an agent
            warn.append(f"key mix: {counts} (target ~6 conflict, ~4 breakage, ~10 none)")
        leaked = [x["seq"] for x in items(r, "requests")
                  if any(w in str(x.get("intent", "")).lower() for w in ("conflict", "break", "seeded"))]
        if leaked:
            warn.append(f"change-requests seq {leaked}: wording may leak the key")
    if (b := docs["binding"]) and docs["change-requests"]:
        if sorted(x["seq"] for x in items(b, "bindings")) != sorted(x["seq"] for x in items(docs["change-requests"], "requests")):
            errs.append("binding: must have exactly one entry per change-request seq")
        if not b.get("domain_version"):
            errs.append("binding: domain_version must name the Phase A model version")
        for x in items(b, "bindings"):
            if not isinstance(x.get("unbindable", False), bool):
                errs.append(f"binding seq {x.get('seq')}: unbindable must be true or false")
            if not x.get("unbindable") and not x.get("elements"):
                errs.append(f"binding seq {x.get('seq')}: elements required unless unbindable")
    for w in warn:
        print("warn:", w)
    return errs


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_manifest(d: Path) -> tuple[dict, list[str]]:
    mp = d / "FROZEN.json"
    if not mp.exists():
        return {"files": {}}, []
    try:
        m = json.loads(mp.read_text())
        if not isinstance(m, dict) or not isinstance(m.get("files"), dict):
            raise ValueError("files must be a mapping")
        return m, []
    except (json.JSONDecodeError, ValueError) as e:
        return {"files": {}}, [f"FROZEN.json is malformed: {e}"]


def _freeze(d: Path, keys: list[str]) -> list[str]:
    errs = validate(d, include_binding="binding" in keys)
    for k in keys:
        doc = load(d, k)
        if doc is None:
            errs.append(f"missing {FILES[k]}")
        elif doc.get("status") != "frozen":
            errs.append(f"{FILES[k]}: set status: frozen yourself before freezing")
    if errs:
        return errs
    manifest_path = d / "FROZEN.json"
    manifest, merrs = read_manifest(d)
    if merrs:
        return merrs
    for k in keys:
        f = FILES[k]
        if f in manifest["files"]:
            if manifest["files"][f]["sha256"] != sha(d / f):
                errs.append(f"{f} already frozen with a different hash; refreezing is not allowed")
            continue
        manifest["files"][f] = {"sha256": sha(d / f),
                                "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if errs:
        return errs
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"frozen: {sorted(manifest['files'])} → {manifest_path}")
    return []


def freeze(d: Path) -> list[str]:
    return _freeze(d, BEFORE_CHECKS)


def freeze_binding(d: Path) -> list[str]:
    manifest, merrs = read_manifest(d)
    if merrs:
        return merrs
    frozen = manifest["files"]
    missing = [FILES[k] for k in BEFORE_CHECKS if FILES[k] not in frozen]
    if missing:
        return [f"stage 1 not done; not frozen yet: {missing}"]
    return _freeze(d, ["binding"])


def verify(d: Path, run: bool = False) -> list[str]:
    if not (d / "FROZEN.json").exists():
        return ["no FROZEN.json: instruments are not frozen"]
    manifest, merrs = read_manifest(d)
    if merrs:
        return merrs
    files = manifest["files"]
    required = [FILES[k] for k in BEFORE_CHECKS] + ([FILES["binding"]] if run else [])
    errs = [f"{f} is not frozen" for f in required if f not in files]
    for f, meta in files.items():
        if not (d / f).exists():
            errs.append(f"{f} missing")
        elif sha(d / f) != meta["sha256"]:
            errs.append(f"{f} changed after freezing")
    return errs


if __name__ == "__main__":
    cmd, d = sys.argv[1], Path(sys.argv[2])
    if cmd == "verify":
        errs = verify(d, run="--run" in sys.argv[3:])
    else:
        errs = {"validate": validate, "freeze": freeze, "freeze-binding": freeze_binding}[cmd](d)
    for e in errs:
        print("error:", e)
    print("ok" if not errs else f"{len(errs)} error(s)")
    sys.exit(1 if errs else 0)
