"""Score M1 Phase B (ADR-0040 §8; run protocol §2–3): the only code that opens the change key
and the binding.

  python -m phase_b grade [--out RUN_DIR]     propose a label for every flag, edit and probe run
  python -m phase_b score [--out RUN_DIR]     the metrics and the pilot verdicts, from the
                                              labels the researcher confirmed

`grade` runs only once every arm has run every change (`--partial` overrides it, for tests and
a look at a dry run; the result says so). It writes `RUN_DIR/scoring/proposed.yaml`:

- **changes**: for each change, every arm's flags from every run, under random labels A, B and C
  (a different order per change; the mapping is in `blind-labels.yaml`, kept apart), graded in
  one pass against the bound key entry: `seeded`, `other-real` or `false-alarm`. A Toprope flag
  that names a bound element gets the script's label too (`script_label`); the grader's is
  `grader_label`; `label` is the one that counts, and the researcher's when they change it. Each
  label's edit is judged too (`implements`, `partial`, `does-not`).
- **probes**: pass or fail for each probe run after each change, judged by the grader against the
  probe's `must` and `must_not` (which no probe agent ever saw).

The researcher reviews `proposed.yaml`, changes any `label`, sets `status: confirmed` and saves it
as `confirmed.yaml`. `score` then computes, per arm and per run (recall and precision with their
mean, minimum and maximum):

- pre-deploy recall: seeded problems (bindable, `problem` not `none`) with a flag labelled
  `seeded` in that run, over all of them; also without handoff-breaking changes, and per type
- pre-deploy precision: flags labelled `seeded` or `other-real`, over all flags of the run
- found after deploy: a seeded problem missed (flagged in at most half the runs), where a probe
  that passed (in most of its runs) before the change fails after it; silent: never surfaced
- iteration time: per change, the median of its timed repeats with the part that bounds it, then
  the median over changes
- the noise floor (the largest spread of an arm's recall), and the Toprope arm's repeat check

and applies the frozen verdict rules (`verdict-rules.yaml`) to the mean numbers, marking a gap
within the noise floor next to the rule it affects: pilot targets, not a link verdict (ADR-0034).
"""

from __future__ import annotations

import json
import random
import re
import secrets
import statistics
from pathlib import Path
from typing import Any

import yaml

from .agent import Transcript
from .arms import prompt

ARMS = ("nl", "structured", "toprope")
LABELS = ("seeded", "other-real", "false-alarm")
BLIND = ("A", "B", "C")
FIDELITY = ("implements", "partial", "does-not")


# -- reading the run ------------------------------------------------------------------------------

def records(run: Path, arm: str) -> dict[int, dict[str, Any]]:
    out = {}
    for f in sorted((run / arm).glob("seq-*/record.json")):
        r = json.loads(f.read_text())
        out[r["seq"]] = r
    return out


def complete(run: Path, seqs: list[int]) -> list[str]:
    """Why the run is not complete yet (every arm, every change, the baseline probes)."""
    missing = []
    for arm in ARMS:
        m = run / arm / "manifest.json"
        if not m.exists():
            missing.append(f"{arm}: not run")
            continue
        man = json.loads(m.read_text())
        if sorted(man["done"]) != sorted(seqs):
            missing.append(f"{arm}: done {sorted(man['done'])}")
    return missing


def load_sealed(instruments: Path) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """The key and the binding, by seq. Opened here and nowhere else (ADR-0040 §8)."""
    key = yaml.safe_load((instruments / "change-key.yaml").read_text())
    binding = yaml.safe_load((instruments / "binding.yaml").read_text())
    return ({e["seq"]: e for e in key["entries"]}, {b["seq"]: b for b in binding["bindings"]})


# -- Toprope findings to binding elements -----------------------------------------------------------

def element_keys(domain: str, where: str) -> set[str]:
    """The binding keys (`<domain>/<interface key>`) a finding's `where` points at."""
    keys: set[str] = set()
    w = where.split("#")[0]
    if m := re.match(r"actions\.([^.]+)(?:\.(preconditions|params)\.([^.]+))?", w):
        keys.add(f"action:{m[1]}")
        if m[2] == "preconditions":
            keys.add(f"precondition:{m[1]}.{m[3]}")
        elif m[2] == "params":
            keys.add(f"param:{m[1]}.{m[3]}")
    elif m := re.match(r"objects\.([^.]+)(?:\.properties\.([^.]+))?", w):
        keys.add(f"object:{m[1]}")
        if m[2]:
            keys.add(f"property:{m[1]}.{m[2]}")
    elif m := re.match(r"transitions\.([^.]+)(?:\.matrix\.([^.]+)(?:\.([^.]+))?)?", w):
        keys.add(f"stages:{m[1]}")
        if m[3]:
            keys.add(f"cell:{m[1]}.{m[2]}.{m[3]}")
            keys.add(f"action:{m[3]}")
    elif m := re.match(r"(?:invariants\.|invariant:)([^.]+)", w):
        keys.add(f"invariant:{m[1]}")
    elif m := re.match(r"scenarios?[.:]([^.]+)", w):
        keys.add(f"scenario:{m[1]}")
    elif m := re.match(r"state:([^.]+)\.(.+)", w):
        keys.update({f"stages:{m[1]}", f"cell:{m[1]}.{m[2]}"})
    elif (m := re.match(r"(link|handoff|role)s?[.:]([^.]+)", w)) or (m := re.match(r"(action|object|property|precondition|param|cell|invariant|stages|fixture):(.+)", w)):
        keys.add(f"{m[1]}:{m[2]}")
    return {f"{domain}/{k}" for k in keys}


def _owners(key: str) -> set[str]:
    """What an element key belongs to: its action and/or object (a cell belongs to both)."""
    dom, _, k = key.partition("/")
    kind, _, rest = k.partition(":")
    parts = rest.split(".")
    if kind == "cell":
        return {f"{dom}/{parts[0]}", f"{dom}/{parts[-1]}"}
    return {f"{dom}/{parts[0]}"}


def binding_match(finding: dict[str, Any], bound: list[str]) -> bool:
    """A Toprope finding touches the elements the change is bound to: the same element, or one
    of the same action or object."""
    keys = element_keys(finding.get("domain", ""), finding.get("where", ""))
    if keys & set(bound):
        return True
    return any(_owners(k) & _owners(b) for k in keys for b in bound if ":" in b and ":" in k.partition("/")[2])


def handoff_breaking(binding: dict[str, Any]) -> bool:
    return any("/handoff:" in e or e.endswith("action:request_delivery") for e in binding.get("elements", []))


# -- grading ------------------------------------------------------------------------------------------

def _json(text: str) -> dict[str, Any] | None:
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            data, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _sealed_context(seq: int, req: dict[str, Any], key: dict[int, Any], binding: dict[int, Any]) -> str:
    k, b = key.get(seq, {}), binding.get(seq, {})
    return (f"Change request {seq}: {req.get('intent')}\n"
            f"Seeded problem (the answer key): {json.dumps({x: k.get(x) for x in ('problem', 'type', 'against')})}\n"
            f"Elements it is bound to: {json.dumps(b.get('elements', []))}; note: {b.get('note', '')}")


def check_runs(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """A change's pre-deploy check runs: five reviews, or the Toprope arm's one (a record from
    before the run protocol has one, under `findings`)."""
    check = rec.get("check") or {}
    if "runs" in check:
        return check["runs"]
    return [{"run": 1, "findings": check.get("findings") or [], "error": check.get("error")}]


def probe_runs(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """The probe runs after a change (a record from before the run protocol has one)."""
    probes = rec.get("probes") or []
    if probes and "probe" in probes[0]:
        return [{"run": 1, "dir": "probes", "results": probes}]
    return probes


def blind_labels(seqs: list[int], rng: random.Random) -> dict[int, dict[str, str]]:
    """Run protocol §2: per change, the arms under random labels, a different order each time."""
    out = {}
    for s in seqs:
        arms = list(ARMS)
        rng.shuffle(arms)
        out[s] = dict(zip(BLIND, arms, strict=True))
    return out


def grade_change(backend: Any, seq: int, req: dict[str, Any], recs: dict[str, dict[str, Any]],
                 labels: dict[str, str], key, binding, out: Path) -> dict[str, Any]:
    """One change, every arm's flags under its blind label, graded in one pass against the bound
    key entry (run protocol §2). Toprope's flags name elements, so a script grades them too."""
    bound = (binding.get(seq) or {}).get("elements", [])
    flags, blocks = [], []
    for letter, arm in labels.items():
        rec = recs.get(arm) or {}
        lines = [f"=== {letter} ===", f"The edit: {(rec.get('edit') or {}).get('diff') or '(no change)'}"]
        for r in check_runs(rec):
            if r.get("error"):
                lines.append(f"(run {r['run']} gave no flags: {r['error']})")
            for i, f in enumerate(r.get("findings") or []):
                fid = f"{letter}.{r['run']}.{i}"
                lines.append(f"{fid}. {json.dumps(f, ensure_ascii=False)}")
                script = "seeded" if arm == "toprope" and binding_match(f, bound) else None
                flags.append({"id": fid, "run": r["run"], "index": i, "flag": f, "script_label": script})
        blocks.append("\n".join(lines))
    user = f"{_sealed_context(seq, req, key, binding)}\n\n" + "\n\n".join(blocks)
    answer = backend.converse(prompt("grade_change"), user, None, Transcript(out / f"seq-{seq:02d}.jsonl"))
    data = _json(answer) or {}
    got = {str(x.get("id")): x for x in data.get("flags", []) if isinstance(x, dict)}
    for f in flags:
        g = got.get(f["id"], {})
        f["grader_label"] = g.get("label") if g.get("label") in LABELS else None
        f["why"] = g.get("why", "" if g else "the grader gave no label")
        # The researcher's label counts; it starts as the script's (an element match) or the
        # grader's. Where they differ, both stay on the record (run protocol §2).
        f["label"] = f["script_label"] or f["grader_label"]
    edits = {str(x.get("label")): x for x in data.get("edits", []) if isinstance(x, dict)}
    return {"seq": seq, "flags": flags,
            "edits": {letter: {"fidelity": (edits.get(letter) or {}).get("fidelity")
                               if (edits.get(letter) or {}).get("fidelity") in FIDELITY else None,
                               "why": (edits.get(letter) or {}).get("why", "")} for letter in labels},
            "grader_error": None if data else "the grader did not answer with JSON"}


def _probe_text(run_dir: Path, result: dict[str, Any]) -> str:
    """What the probe agent did, from its transcript: tool calls, their results, messages, answer."""
    lines = []
    t = run_dir / result.get("transcript", "")
    if t.is_file():
        for row in t.read_text().splitlines():
            e = json.loads(row)
            if e["kind"] == "reply":
                for b in e.get("content") or []:
                    if b.get("type") == "tool_use":
                        lines.append(f"CALL {b.get('name')} {json.dumps(b.get('input'), ensure_ascii=False)[:600]}")
                    elif b.get("type") == "text" and b.get("text"):
                        lines.append(f"SAYS {b['text'][:600]}")
            elif e["kind"] == "tool":
                lines.append(f"RESULT {str(e.get('output'))[:600]}")
    lines.append(f"MESSAGES TO THE OWNER {json.dumps(result.get('messages_to_owner'), ensure_ascii=False)[:2000]}")
    lines.append(f"FINAL ANSWER {str(result.get('answer'))[:2000]}")
    if result.get("error"):
        lines.append(f"ERROR {result['error']}")
    return "\n".join(lines)


def grade_probe(backend: Any, probe: dict[str, Any], run_dir: Path, result: dict[str, Any], out: Path) -> dict[str, Any]:
    if result.get("error"):
        # The conversation did not complete: not the agent's pass or fail. The researcher decides
        # (a deployed change that broke the tools is a failure; an outage is not).
        return {"probe": probe["id"], "passed": None, "why": f"the probe did not complete: {result['error']}",
                "error": result["error"]}
    user = (f"Probe {probe['id']}. Task given to the agent: {probe['task']}\n"
            f"Starting state: {probe['starting_state']}\n"
            f"It must: {json.dumps(probe.get('must', []))}\nIt must not: {json.dumps(probe.get('must_not', []))}\n"
            f"Notes: {probe.get('notes', '')}\n\n--- What the agent did ---\n{_probe_text(run_dir, result)}")
    answer = backend.converse(prompt("grade_probe"), user, None, Transcript(out))
    data = _json(answer) or {}
    passed = data.get("passed")
    return {"probe": probe["id"], "passed": passed if isinstance(passed, bool) else None,
            "why": data.get("why", ""), "error": result.get("error")}


def grade(run: Path, instruments: Path, backend: Any, requests: list[dict[str, Any]], partial: bool = False,
          seed: int | None = None) -> Path:
    seqs = [r["seq"] for r in requests]
    missing = complete(run, seqs)
    if missing and not partial:
        raise SystemExit("the key opens only after every arm has run every change:\n" + "\n".join(missing))
    key, binding = load_sealed(instruments)
    probes = {p["id"]: p for p in yaml.safe_load((instruments / "probe-suite.yaml").read_text())["probes"]}
    out = run / "scoring"
    tr = out / "transcripts"
    recs = {arm: records(run, arm) for arm in ARMS}
    seed = secrets.randbits(32) if seed is None else seed
    labels = blind_labels(seqs, random.Random(seed))
    out.mkdir(parents=True, exist_ok=True)
    # The mapping is kept apart from what is graded (run protocol §2); `score` joins them.
    (out / "blind-labels.yaml").write_text(
        "# Which arm each label stands for, per change. Do not open it while grading.\n"
        + yaml.safe_dump({"seed": seed, "labels": labels}, sort_keys=False))
    reqs = {r["seq"]: r for r in requests}
    changes = [grade_change(backend, s, reqs[s], {a: recs[a].get(s, {}) for a in ARMS}, labels[s], key, binding, tr)
               for s in seqs if any(s in recs[a] for a in ARMS)]
    probe_rows: dict[str, list[dict[str, Any]]] = {}
    for arm in ARMS:
        rows = probe_rows.setdefault(arm, [])
        for seq, rec in sorted(recs[arm].items()):
            for pr in probe_runs(rec):
                for res in pr["results"]:
                    g = grade_probe(backend, probes[res["probe"]], run / arm / f"seq-{seq:02d}" / pr["dir"], res,
                                    tr / f"{arm}-seq-{seq:02d}-run-{pr['run']}-{res['probe']}.jsonl")
                    rows.append({"seq": seq, "run": pr["run"], **g})
    proposal: dict[str, Any] = {"status": "proposed", "partial": bool(missing), "missing": missing,
                                "changes": changes, "probes": probe_rows}
    path = out / "proposed.yaml"
    path.write_text("# Proposed by the script (element matches) and the grader (ADR-0040 §8; run protocol §2).\n"
                    "# Each change's flags are under blind labels (A, B, C); the mapping is in blind-labels.yaml.\n"
                    "# Review every `label` (keep `script_label` and `grader_label` as they are), set\n"
                    "# `status: confirmed`, and save as confirmed.yaml; `score` reads only that file.\n"
                    + yaml.safe_dump(proposal, sort_keys=False, allow_unicode=True, width=110))
    return path


# -- metrics and verdicts --------------------------------------------------------------------------------

def _seeded(key: dict[int, Any], binding: dict[int, Any]) -> list[int]:
    return [s for s, k in sorted(key.items()) if k.get("problem") not in (None, "none")
            and not (binding.get(s) or {}).get("unbindable")]


def spread(values: list[float | None]) -> dict[str, Any]:
    """A number with its spread over runs (run protocol §3)."""
    xs = [v for v in values if v is not None]
    if not xs:
        return {"runs": values, "mean": None, "min": None, "max": None}
    return {"runs": values, "mean": round(statistics.mean(xs), 4), "min": round(min(xs), 4), "max": round(max(xs), 4)}


def _by_arm(graded: dict[str, Any], labels: dict[int, dict[str, str]]) -> dict[str, dict[int, dict[str, Any]]]:
    """The confirmed grades of each change, back under each arm's name."""
    out: dict[str, dict[int, dict[str, Any]]] = {a: {} for a in ARMS}
    for c in graded["changes"]:
        for letter, arm in labels[c["seq"]].items():
            out[arm][c["seq"]] = {"flags": [f for f in c["flags"] if f["id"].split(".")[0] == letter],
                                  "edit": c["edits"].get(letter) or {}}
    return out


def arm_metrics(arm: str, changes: dict[int, dict[str, Any]], probes: list[dict[str, Any]], recs: dict[int, Any],
                key, binding) -> dict[str, Any]:
    seeded = _seeded(key, binding)
    runs = sorted({r["run"] for s, rec in recs.items() if s > 0 for r in check_runs(rec)}) or [1]

    def flagged_in(run: int) -> set[int]:
        return {s for s in seeded if any(f["label"] == "seeded" and f["run"] == run
                                         for f in changes.get(s, {}).get("flags", []))}

    def recall(of: list[int], run: int) -> float | None:
        return round(len([s for s in of if s in flagged_in(run)]) / len(of), 4) if of else None

    def precision(run: int) -> float | None:
        fs = [f for c in changes.values() for f in c["flags"] if f["run"] == run]
        return round(len([f for f in fs if f["label"] in ("seeded", "other-real")]) / len(fs), 4) if fs else None

    # A seeded problem counts as flagged before deploy when most of the arm's runs flagged it; the
    # rest are missed, and the probes tell whether they surfaced after deploy.
    flagged = {s for s in seeded if sum(s in flagged_in(r) for r in runs) * 2 > len(runs)}
    no_handoff = [s for s in seeded if not handoff_breaking(binding.get(s, {}))]
    by_type: dict[str, list[int]] = {}
    by_design: dict[str, list[int]] = {}
    for s in seeded:
        by_type.setdefault(str(key[s].get("type") or "unknown"), []).append(s)
        by_design.setdefault(str(key[s].get("designed_for_checks", "unknown")), []).append(s)
    # A probe passes after a change when most of its runs passed.
    votes: dict[int, dict[str, list[bool]]] = {}
    for p in probes:
        if isinstance(p.get("passed"), bool):
            votes.setdefault(p["seq"], {}).setdefault(p["probe"], []).append(p["passed"])
    probe_at = {s: {pid: sum(v) * 2 > len(v) for pid, v in ps.items()} for s, ps in votes.items()}
    probe_runs_ = sorted({p.get("run", 1) for p in probes})
    pass_rate = [round(statistics.mean([p["passed"] for p in probes if p.get("run", 1) == r and p["seq"] > 0
                                        and isinstance(p["passed"], bool)] or [0]), 4) for r in probe_runs_]
    missed = [s for s in seeded if s not in flagged]
    after_deploy: dict[int, list[str]] = {}
    seqs_seen = sorted(probe_at)
    for i, t_ in enumerate(seqs_seen[1:], 1):
        for pid, ok in probe_at[t_].items():
            if ok is not False or probe_at[seqs_seen[i - 1]].get(pid) is not True:
                continue
            last_fail = max((s for s in seqs_seen[:i] if probe_at[s].get(pid) is False), default=0)
            for s in missed:
                if last_fail < s <= t_:
                    after_deploy.setdefault(s, []).append(pid)
    after_deploy = {s: sorted(set(v)) for s, v in sorted(after_deploy.items())}
    breakages = [s for s in seeded if key[s].get("problem") == "breakage"]
    rec_spread = spread([recall(seeded, r) for r in runs])
    out: dict[str, Any] = {
        "seeded": len(seeded), "runs": len(runs), "flagged": sorted(flagged),
        "recall": rec_spread["mean"], "recall_spread": rec_spread,
        "recall_without_handoff": spread([recall(no_handoff, r) for r in runs])["mean"],
        "recall_by_type": {t: spread([recall(v, r) for r in runs])["mean"] for t, v in sorted(by_type.items())},
        "recall_by_designed_for_checks": {t: spread([recall(v, r) for r in runs])["mean"]
                                          for t, v in sorted(by_design.items())},
        "findings": len([f for c in changes.values() for f in c["flags"]]),
        "precision": spread([precision(r) for r in runs])["mean"], "precision_spread": spread([precision(r) for r in runs]),
        "found_after_deploy": after_deploy, "silent": sorted(s for s in missed if s not in after_deploy),
        "breakages_found_only_after_deploy": round(len([s for s in breakages if s in after_deploy]) / len(breakages), 4)
        if breakages else None,
        "edit_fidelity": {f: len([c for c in changes.values() if c["edit"].get("fidelity") == f]) for f in FIDELITY},
        "probe_pass_rate": spread(pass_rate),
        "probes_failed": {s: sorted(pid for pid, ok in v.items() if ok is False) for s, v in sorted(probe_at.items())},
        "handoff_probe_P07_passes_throughout": all(v.get("P07") is True for s, v in probe_at.items() if s > 0)
        if probe_at else None,
    }
    out.update(_times(arm, recs))
    if arm == "toprope":
        out["undeployable"] = sorted(s for s, r in recs.items() if s > 0 and r.get("deploy", {}).get("domains")
                                     and not r["deploy"].get("deployed"))
        out["handoff_breaking_caught"] = {s: s in flagged for s in seeded if handoff_breaking(binding.get(s, {}))}
        out["repeat_same"] = {s: r["check"]["repeat"]["same"] for s, r in sorted(recs.items())
                              if "repeat" in (r.get("check") or {})}
    return out


def _times(arm: str, recs: dict[int, Any]) -> dict[str, Any]:
    """Iteration time (run protocol §3): per change, the median of its timed repeats, with their
    spread and what bounds them; then the median over changes."""
    per_change: dict[int, dict[str, Any]] = {}
    for s, r in sorted(recs.items()):
        if s <= 0:
            continue
        timed = (r.get("check") or {}).get("timed")
        if timed:
            xs = [t["seconds"] for t in timed]
            limiters = [t["limiter"] for t in timed if t.get("limiter")]
            per_change[s] = {"median_s": round(statistics.median(xs), 2), "min_s": round(min(xs), 2),
                             "max_s": round(max(xs), 2),
                             "limiter": max(set(limiters), key=limiters.count) if limiters else None}
        elif "edit_to_checked" in r.get("seconds", {}):
            per_change[s] = {"median_s": round(r["seconds"]["edit_to_checked"], 2), "limiter": None}
    medians = [c["median_s"] for c in per_change.values()]
    return {"median_edit_to_checked_s": round(statistics.median(medians), 2) if medians else None,
            "iteration_time_by_change": per_change}


def noise_floor(m: dict[str, dict[str, Any]]) -> float | None:
    """The largest min-to-max spread of an arm's recall over runs (run protocol §3)."""
    spans = [x["recall_spread"]["max"] - x["recall_spread"]["min"] for x in m.values()
             if x.get("recall_spread", {}).get("max") is not None]
    return round(max(spans), 4) if spans else None


def verdicts(m: dict[str, dict[str, Any]], rules: dict[str, Any]) -> dict[str, Any]:
    """The frozen pilot rules (verdict-rules.yaml), applied as they are to the arms' mean numbers;
    a gap smaller than the noise floor is marked next to the rule it affects (run protocol,
    Decision 1)."""
    it = rules["iterate"]
    t, nl, st = m["toprope"], m["nl"], m["structured"]
    r = {k: x["recall"] for k, x in m.items()}
    if None in r.values():
        return {"iterate": "inconclusive", "why": "no seeded problems to measure recall on", "handoff": None}
    sup = it["supports"]
    gap_nl, gap_st = t["recall"] - nl["recall"], t["recall"] - st["recall"]
    most_after = all((x["breakages_found_only_after_deploy"] or 0) > 0.5 for x in (nl, t))   # in both arms
    supports = (t["recall"] >= sup["toprope_recall_min"] and (t["precision"] or 0) >= sup["toprope_precision_min"]
                and gap_nl >= sup["nl_recall_gap_min"] and gap_st >= sup["structured_recall_gap_min"]
                and t["median_edit_to_checked_s"] is not None
                and t["median_edit_to_checked_s"] <= sup["median_iteration_minutes_max"] * 60)
    weakens = (gap_nl <= it["weakens"]["nl_within"] or (t["precision"] or 0) < it["weakens"]["toprope_precision_below"]
               or (it["weakens"].get("most_found_after_deploy") and most_after))
    if gap_nl >= sup["nl_recall_gap_min"] and gap_st < it["narrowed_if_structured_gap_below"]:
        iterate = "narrowed (recorded as weakened for the compiler claim)"
    elif supports:
        iterate = "supports (pilot target met)"
    elif weakens:
        iterate = "weakens"
    else:
        iterate = it.get("else", "inconclusive")
    ho = rules["handoff"]
    caught = t.get("handoff_breaking_caught") or {}
    p07 = t["handoff_probe_P07_passes_throughout"]
    if caught:
        handoff = "supports (partial)" if all(caught.values()) and p07 else ho.get("else", "inconclusive")
    else:
        handoff = (ho["if_none_seeded"]["report"] if p07 else ho.get("else", "inconclusive"))
    floor = noise_floor(m)
    within = {}
    if floor is not None:
        for name, gap, rule in (("gap_nl", gap_nl, "iterate.supports.nl_recall_gap_min / weakens.nl_within"),
                                ("gap_structured", gap_st,
                                 "iterate.supports.structured_recall_gap_min / narrowed_if_structured_gap_below")):
            if abs(gap) < floor:
                within[name] = f"within run-to-run noise ({round(gap, 4)} < noise floor {floor}); affects {rule}"
    return {"iterate": iterate, "handoff": handoff,
            "not_measured_here": ["hand_edits_to_generated_max (the self-compile result, reported separately)"],
            "numbers": {"recall": r, "gap_nl": round(gap_nl, 4), "gap_structured": round(gap_st, 4),
                        "toprope_precision": t["precision"], "median_edit_to_checked_s": t["median_edit_to_checked_s"],
                        "noise_floor": floor},
            "within_noise": within,
            "steps": "one run's recall moves in steps of 1/seeded" + (f" ({round(1 / t['seeded'], 4)})"
                                                                       if t.get("seeded") else ""),
            "note": "M1 pilot targets (ADR-0034): reported, not a link verdict; the claim-status table does not change"}


def score(run: Path, instruments: Path) -> dict[str, Any]:
    conf = run / "scoring/confirmed.yaml"
    if not conf.exists():
        raise SystemExit(f"no {conf}: the researcher confirms the grader's labels first (see proposed.yaml)")
    graded = yaml.safe_load(conf.read_text())
    if graded.get("status") != "confirmed":
        raise SystemExit(f"{conf}: set `status: confirmed` once every label is reviewed")
    unlabelled = [(c["seq"], f["id"]) for c in graded["changes"] for f in c["flags"] if f.get("label") not in LABELS]
    unlabelled += [(a, p["seq"], p.get("run", 1), p["probe"]) for a, ps in graded["probes"].items() for p in ps
                   if not isinstance(p.get("passed"), bool)]
    if unlabelled:
        raise SystemExit(f"{len(unlabelled)} item(s) still have no label, e.g. {unlabelled[:5]}")
    labels = {int(s): v for s, v in yaml.safe_load((run / "scoring/blind-labels.yaml").read_text())["labels"].items()}
    key, binding = load_sealed(instruments)
    rules = yaml.safe_load((instruments / "verdict-rules.yaml").read_text())
    by_arm = _by_arm(graded, labels)
    m = {arm: arm_metrics(arm, by_arm[arm], graded["probes"].get(arm, []), records(run, arm), key, binding)
         for arm in ARMS}
    disagree = [(c["seq"], f["id"]) for c in graded["changes"] for f in c["flags"]
                if f.get("script_label") and f.get("label") != f["script_label"]]
    result = {"partial": graded.get("partial", False), "metrics": m, "verdicts": verdicts(m, rules),
              "noise_floor": noise_floor(m), "script_and_researcher_disagree": disagree,
              "unbindable": sorted(s for s, b in binding.items() if b.get("unbindable"))}
    (run / "scoring/metrics.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result
