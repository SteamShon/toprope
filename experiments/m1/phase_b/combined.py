"""The Toprope arm with its LLM review: the compiler's flags and an LLM review of the same edit.

The Toprope arm as first run measured the compiler alone: its change check had no
natural-language checker. Toprope's design pairs the compiler with an LLM (ADR-0009), so the fair
comparison with the NL skill is the declarations, their scenarios, the compiler and an LLM review
together. This measures it on the edits the Toprope arm already made, so no change is made again:

- For each change, the declarations after the Toprope arm's edit (its commit, from the sandbox's
  commit store), with the composition, are reviewed five times with the frozen review prompt, as
  the structured arm's are (run protocol §3).
- Each run's flags are the compiler's flags (one run, derandomized) and that review's findings.

It writes a run directory with the NL and structured arms copied as they are and the combined arm
as `toprope`, so `grade` and `score` run on it unchanged, blind across the three arms. It is an
arm added after M1's first scoring, and the M1 report says so.

  uv run python -m phase_b combine-toprope --model M     # runs/phase-b → runs/phase-b-combined
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .agent import Transcript
from .arms import parse_findings, prompt, request_text
from .backend import Backend
from .runlog import RunLog, log_path
from .toprope_arm import COMPOSITION, DOMAINS

REVIEWED_AS = "the YAML declarations of two domains and the composition that joins them"   # as structured


def _declaration(root: Path, d: str, cid: str) -> str:
    from toprope.commits import CommitStore
    with tempfile.TemporaryDirectory() as tmp:
        return CommitStore(root / ".toprope/commits").export(d, cid, Path(tmp) / f"{d}.domain.yaml").read_text()


def _files(texts: dict[str, str], composition: str) -> str:
    named = {f"{d}/{d}.domain.yaml": texts[d] for d in DOMAINS}
    named["toprope-self.composition.yaml"] = composition
    return "\n\n".join(f"=== {n} ===\n{t}" for n, t in sorted(named.items()))


def combine(source: Path, dest: Path, backend: Backend, reviews: int = 5,
            materials: Path | None = None) -> dict[str, Any]:
    """Copy the NL and structured arms, and build the combined Toprope arm in `dest` (resumable:
    a change whose reviews are done is not reviewed again)."""
    dest.mkdir(parents=True, exist_ok=True)
    for arm in ("nl", "structured"):
        if not (dest / arm).exists():
            shutil.copytree(source / arm, dest / arm, ignore=shutil.ignore_patterns("workspace", "deployed"))
    src = source / "toprope"
    root = src / "sandbox"
    out = dest / "toprope"
    out.mkdir(exist_ok=True)
    shutil.copy(src / "manifest.json", out / "manifest.json")
    composition = (root / COMPOSITION).read_text()
    base = materials or Path(__file__).resolve().parents[1] / "arms/toprope"
    current = {d: (base / "domains" / d / f"{d}.domain.yaml").read_text() for d in DOMAINS}
    log = RunLog(log_path(dest))
    done: list[int] = []
    for f in sorted(src.glob("seq-*/record.json")):
        rec = json.loads(f.read_text())
        seq = rec["seq"]
        d_out = out / f"seq-{seq:02d}"
        d_out.mkdir(exist_ok=True)
        if seq <= 0:
            shutil.copy(f, d_out / "record.json")
            continue
        check = rec.get("check") or {}
        after = dict(current)
        for d, c in (check.get("commits") or {}).items():
            after[d] = _declaration(root, d, c["commit"])
        target = d_out / "record.json"
        prior = json.loads(target.read_text()) if target.exists() else {}
        llm = (prior.get("check") or {}).get("llm_runs")
        if not llm:
            user = (f"{request_text(rec)}\n\n--- The diff ---\n{rec['edit'].get('diff') or '(no change)'}\n\n"
                    f"--- Every file after the change ---\n{_files(after, composition)}")
            llm = []
            for k in range(1, reviews + 1):
                t = time.monotonic()
                answer = backend.converse(prompt("review", arm=REVIEWED_AS), user, None,
                                          Transcript(d_out / f"llm-review-{k}.jsonl"))
                findings, error = parse_findings(answer)
                llm.append({"run": k, "findings": [{**x, "from": "llm"} for x in findings], "error": error,
                            "seconds": time.monotonic() - t, "transcript": f"llm-review-{k}.jsonl"})
                log.append("toprope", seq, k, "review", d_out / f"llm-review-{k}.jsonl",
                           f"error: {error}" if error else f"{len(findings)} finding(s)")
        compiler = [{**x, "from": "compiler"} for x in check.get("findings") or []]
        rec["check"] = {**check, "compiler": compiler, "llm_runs": llm,
                        "runs": [{"run": r["run"], "findings": compiler + r["findings"], "error": r["error"]}
                                 for r in llm]}
        target.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
        if any(r.get("deployed") for r in (rec.get("deploy") or {}).get("domains", {}).values()):
            for d, c in (check.get("commits") or {}).items():
                if (rec["deploy"]["domains"].get(d) or {}).get("deployed"):
                    current[d] = after[d]
        done.append(seq)
    return {"combined": done, "to": str(dest)}
