"""Validate, freeze and verify experiment instruments.

Usage (from the repo root):
  uv run --with pyyaml python experiments/tools/instruments.py validate experiments/m1/instruments
  uv run --with pyyaml python experiments/tools/instruments.py freeze   experiments/m1/instruments
  uv run --with pyyaml python experiments/tools/instruments.py verify   experiments/m1/instruments

validate  checks the filled files (not *.template.yaml) for format and cross-file consistency.
freeze    is run by the researcher only: requires every file's status to be `frozen`, then writes
          FROZEN.json with a sha256 per file. Commit it in the researcher's own commit.
verify    fails if any frozen file changed after freezing. The harness runs it before every M1 run.
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
BEFORE_CHECKS = ["gold-scenarios", "probe-suite", "change-requests", "change-key", "verdict-rules"]
ANSWER_KINDS = {"yes_no", "outcome", "state", "actors", "free_text"}
PROBLEMS = {"none", "conflict", "breakage"}
TYPES = {"conflicts-with-rule", "breaks-reference", "breaks-scenario", "breaks-past-behavior",
         "strands-objects"}


def load(d: Path, key: str):
    p = d / FILES[key]
    return yaml.safe_load(p.read_text()) if p.exists() else None


def validate(d: Path) -> list[str]:
    errs: list[str] = []
    warn: list[str] = []
    docs = {k: load(d, k) for k in FILES}
    for k in BEFORE_CHECKS:
        if docs[k] is None:
            errs.append(f"missing {FILES[k]}")
        elif docs[k].get("instrument") != k:
            errs.append(f"{FILES[k]}: instrument must be '{k}'")
    if g := docs["gold-scenarios"]:
        ids = [s.get("id") for s in g.get("scenarios", [])]
        if len(ids) != len(set(ids)):
            errs.append("gold-scenarios: duplicate ids")
        for s in g.get("scenarios", []):
            if s.get("answer", {}).get("kind") not in ANSWER_KINDS:
                errs.append(f"gold {s.get('id')}: answer.kind must be one of {sorted(ANSWER_KINDS)}")
            if "<" in str(s.get("question", "")):
                errs.append(f"gold {s.get('id')}: question still a placeholder")
        held = sum(1 for s in g.get("scenarios", []) if s.get("held_out"))
        n = len(ids)
        if n and not (0.35 <= held / n <= 0.65):
            warn.append(f"gold: {held}/{n} held out (target about half)")
    if (r := docs["change-requests"]) and (k := docs["change-key"]):
        seqs = [x["seq"] for x in r.get("requests", [])]
        kseqs = [x["seq"] for x in k.get("entries", [])]
        if seqs != sorted(seqs) or len(seqs) != len(set(seqs)):
            errs.append("change-requests: seq must be unique and increasing")
        if sorted(seqs) != sorted(kseqs):
            errs.append("change-key: must have exactly one entry per change-request seq")
        for e in k.get("entries", []):
            if e.get("problem") not in PROBLEMS:
                errs.append(f"key seq {e.get('seq')}: problem must be one of {sorted(PROBLEMS)}")
            t = str(e.get("type", ""))
            if e.get("problem") != "none" and not (t in TYPES or t.startswith("other:")):
                errs.append(f"key seq {e.get('seq')}: type must be one of {sorted(TYPES)} or other:<text>")
        counts = {p: sum(1 for e in k.get("entries", []) if e.get("problem") == p) for p in PROBLEMS}
        warn.append(f"key mix: {counts} (target ~6 conflict, ~4 breakage, ~10 none)")
        leaked = [x["seq"] for x in r.get("requests", [])
                  if any(w in str(x.get("intent", "")).lower() for w in ("conflict", "break", "seeded"))]
        if leaked:
            warn.append(f"change-requests seq {leaked}: wording may leak the key")
    if (b := docs["binding"]) and docs["change-requests"]:
        if sorted(x["seq"] for x in b.get("bindings", [])) != sorted(x["seq"] for x in docs["change-requests"]["requests"]):
            errs.append("binding: must have exactly one entry per change-request seq")
    for w in warn:
        print("warn:", w)
    return errs


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def freeze(d: Path) -> list[str]:
    errs = validate(d)
    present = [k for k in FILES if (d / FILES[k]).exists()]
    for k in present:
        if load(d, k).get("status") != "frozen":
            errs.append(f"{FILES[k]}: set status: frozen yourself before freezing")
    if errs:
        return errs
    manifest_path = d / "FROZEN.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    for k in present:
        f = FILES[k]
        if f in manifest["files"] and manifest["files"][f]["sha256"] != sha(d / f):
            errs.append(f"{f} already frozen with a different hash; refreezing is not allowed")
        manifest["files"].setdefault(f, {"sha256": sha(d / f),
                                         "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    if errs:
        return errs
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"froze {len(manifest['files'])} files → {manifest_path}")
    return []


def verify(d: Path) -> list[str]:
    mp = d / "FROZEN.json"
    if not mp.exists():
        return ["no FROZEN.json: instruments are not frozen"]
    errs = []
    for f, meta in json.loads(mp.read_text())["files"].items():
        if not (d / f).exists():
            errs.append(f"{f} missing")
        elif sha(d / f) != meta["sha256"]:
            errs.append(f"{f} changed after freezing")
    return errs


if __name__ == "__main__":
    cmd, d = sys.argv[1], Path(sys.argv[2])
    errs = {"validate": validate, "freeze": freeze, "verify": verify}[cmd](d)
    for e in errs:
        print("error:", e)
    print("ok" if not errs else f"{len(errs)} error(s)")
    sys.exit(1 if errs else 0)
