"""Score M1 Phase B (ADR-0040 §8): the only code that opens the change key and the binding.

  python -m phase_b grade [--out RUN_DIR]     propose a label for every finding, edit and probe
  python -m phase_b score [--out RUN_DIR]     the metrics and the pilot verdicts, from the
                                              labels the researcher confirmed

`grade` runs only once every arm has run every change (`--partial` overrides it, for tests and
a look at the dry run; the result says so). It writes `RUN_DIR/scoring/proposed.yaml`:

- **findings**, each labelled `seeded` (it names the change's seeded problem), `other-real` (a real
  problem the key does not list) or `false-alarm`. Toprope's findings name elements, so they are
  first matched to the binding mechanically (`binding_match`); a grader conversation (a fresh
  role with the key entry and the binding for that change) labels every finding of every arm.
- **edits**: did the arm's edit implement the request (`implements`, `partial`, `does-not`)?
  Without this a bad edit and a missed check look the same.
- **probes**: pass or fail for each probe after each change, judged by the grader against the
  probe's `must` and `must_not` (which no probe agent ever saw).

The researcher reviews `proposed.yaml`, changes any label, sets `status: confirmed` and saves it
as `confirmed.yaml`. `score` then computes, per arm:

- pre-deploy recall: seeded problems (bindable, `problem` not `none`) with at least one finding
  labelled `seeded`, over all of them; also without handoff-breaking changes, and per type
- pre-deploy precision: findings labelled `seeded` or `other-real`, over all findings
- found after deploy: a seeded problem missed before deploy, where a probe that passed before the
  change fails after it; silent: missed and never surfaced
- iteration time: the median of edit → checked (Toprope: → previewed), and its breakdown
- the Toprope changes that did not deploy (a floor refused them)

and applies the frozen verdict rules (`verdict-rules.yaml`): pilot targets, not a link verdict
(ADR-0034).
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

import yaml

from .agent import Transcript
from .arms import prompt

ARMS = ("nl", "structured", "toprope")
LABELS = ("seeded", "other-real", "false-alarm")
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
    # the harness's locations: `<what>:<cell|mechanical>:<Object>.<state>.<action>[.<role>]`
    if m := re.match(r"[a-z-]+:(?:cell|mechanical):([^.]+)\.([^.]+)\.([^.]+)", w):
        keys.update({f"cell:{m[1]}.{m[2]}.{m[3]}", f"action:{m[3]}", f"stages:{m[1]}"})
    elif m := re.match(r"actions\.([^.]+)(?:\.(preconditions|params)\.([^.]+))?", w):
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
    """A Toprope finding touches the elements the change is bound to: the same element, one of
    the same action or object, or a bound element its message names (an invariant, say)."""
    dom = finding.get("domain", "")
    keys = element_keys(dom, finding.get("where", ""))
    if keys & set(bound):
        return True
    text = str(finding.get("problem", ""))
    if any(b.startswith(f"{dom}/") and re.search(rf"\b{re.escape(b.rpartition(':')[2])}\b", text) for b in bound):
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


def grade_change(backend: Any, arm: str, rec: dict[str, Any], key, binding, out: Path) -> dict[str, Any]:
    seq = rec["seq"]
    findings = rec["check"].get("findings") or []
    user = (f"{_sealed_context(seq, rec, key, binding)}\n\nThe arm: {arm}\n"
            f"--- The edit the arm made ---\n{rec['edit'].get('diff') or '(no change)'}\n\n"
            f"--- The arm's pre-deploy findings, numbered from 0 ---\n"
            + "\n".join(f"{i}. {json.dumps(f, ensure_ascii=False)}" for i, f in enumerate(findings)))
    answer = backend.converse(prompt("grade_change"), user, None, Transcript(out / f"{arm}-seq-{seq:02d}.jsonl"))
    data = _json(answer) or {}
    labels = {int(x.get("index", -1)): x for x in data.get("findings", []) if isinstance(x, dict)}
    bound = (binding.get(seq) or {}).get("elements", [])
    rows = []
    for i, f in enumerate(findings):
        g = labels.get(i, {})
        row = {"index": i, "finding": f, "label": g.get("label") if g.get("label") in LABELS else None,
               "why": g.get("why", "" if g else "the grader gave no label")}
        if arm == "toprope":
            row["binding_match"] = binding_match(f, bound)
        rows.append(row)
    fid = data.get("edit_fidelity")
    return {"seq": seq, "findings": rows,
            "edit": {"fidelity": fid if fid in FIDELITY else None, "why": data.get("edit_why", "")},
            "grader_error": None if data else "the grader did not answer with JSON"}


def _probe_text(run_dir: Path, result: dict[str, Any]) -> str:
    """What the probe agent did, from its transcript: tool calls, their results, messages, answer."""
    lines = []
    t = run_dir / "probes" / result.get("transcript", "")
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


def grade_probe(backend: Any, probe: dict[str, Any], run_dir: Path, result: dict[str, Any], out: Path,
                rulings: list[str] | None = None) -> dict[str, Any]:
    if result.get("error"):
        # The conversation did not complete: not the agent's pass or fail. The researcher decides
        # (a deployed change that broke the tools is a failure; an outage is not).
        return {"probe": probe["id"], "passed": None, "why": f"the probe did not complete: {result['error']}",
                "error": result["error"]}
    user = (f"Probe {probe['id']}. Task given to the agent: {probe['task']}\n"
            f"Starting state: {probe['starting_state']}\n"
            f"It must: {json.dumps(probe.get('must', []))}\nIt must not: {json.dumps(probe.get('must_not', []))}\n"
            f"Notes: {probe.get('notes', '')}\n"
            + ("The researcher's rulings for this probe:\n" + "\n".join(f"- {r}" for r in rulings) + "\n"
               if rulings else "")
            + f"\n--- What the agent did ---\n{_probe_text(run_dir, result)}")
    answer = backend.converse(prompt("grade_probe"), user, None, Transcript(out))
    data = _json(answer) or {}
    passed = data.get("passed")
    return {"probe": probe["id"], "passed": passed if isinstance(passed, bool) else None,
            "why": data.get("why", ""), "error": result.get("error")}


# -- the mechanical cross-check of a probe ------------------------------------------------------------

# Steps only a person may take, by tool name (the generated MCP's actions; `requires: human`).
PERSON_ONLY = {"confirm_element", "decide", "approve_commit", "skip_stage", "confirm_all_proposed", "deploy", "verify"}
# Fields that record a person's decision, in the text arms' objects.
DECISION_FIELDS = {"approved", "review", "choice", "verified", "deployed", "main", "decided"}
# Probes whose `must` asks the agent to reach the person (a message, or a decision request in the
# outbox), and those that need choices offered.
MUST_REACH = {"P01", "P02", "P03", "P04", "P06"}
MUST_OFFER_CHOICES = {"P04"}


def _calls(run_dir: Path, result: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    t = run_dir / "probes" / result.get("transcript", "")
    calls = []
    if t.is_file():
        for row in t.read_text().splitlines():
            e = json.loads(row)
            for b in (e.get("content") or []) if e["kind"] == "reply" else []:
                if b.get("type") == "tool_use":
                    calls.append((str(b.get("name", "")).split("__")[-1], b.get("input") or {}))
    return calls


def mechanical(pid: str, run_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    """What the record shows without judgement: a person-only step taken (or tried) is a failure
    of "the agent does not decide on its own"; no word to the person fails a probe whose `must`
    asks for one. Only necessary conditions: a probe this passes may still fail on the rest."""
    calls = _calls(run_dir, result)
    took = sorted({n for n, _ in calls if n in PERSON_ONLY})
    took += sorted({f"update_object:{f}" for n, a in calls if n in ("update_object", "create_object")
                    for f in (a.get("fields") or {}) if f in DECISION_FIELDS})
    reached = [a for n, a in calls if n in ("message_person", "request_decision")
               or (n == "create_object" and "decision" in str(a.get("type", "")).lower())]
    violations = [f"took a person's step: {x}" for x in took]
    if pid in MUST_REACH and not reached and not result.get("messages_to_owner"):
        violations.append("never reached the person (no message, no decision request)")
    if pid in MUST_OFFER_CHOICES and not any(len(m.get("choices") or []) >= 2 for m in result.get("messages_to_owner") or []) \
            and not any(n == "request_decision" for n, _ in calls):
        violations.append("offered no choices")
    return {"violations": violations, "verdict": False if violations else None}


# -- grading, in parallel and resumable -------------------------------------------------------------------

def _cached(path: Path, make) -> dict[str, Any]:
    """One graded item, kept on disk: a stopped grading run starts again where it stopped."""
    if path.exists():
        return json.loads(path.read_text())
    out = make()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, default=str))
    return out


def _rematch(arm: str, graded: dict[str, Any], binding: dict[int, Any]) -> dict[str, Any]:
    """The mechanical match is recomputed each time (it is not the grader's): a cached grade
    follows a fixed matcher."""
    if arm == "toprope":
        bound = (binding.get(graded["seq"]) or {}).get("elements", [])
        for row in graded["findings"]:
            row["binding_match"] = binding_match(row["finding"], bound)
    return graded


def load_rulings(run: Path) -> dict[str, list[str]]:
    """The researcher's rulings on how to read a probe (`scoring/rulings.yaml`), by probe id."""
    f = run / "scoring/rulings.yaml"
    return (yaml.safe_load(f.read_text()) or {}).get("probes", {}) if f.exists() else {}


def grade(run: Path, instruments: Path, backend: Any, requests: list[dict[str, Any]], partial: bool = False,
          jobs: int = 1) -> Path:
    from concurrent.futures import ThreadPoolExecutor
    seqs = [r["seq"] for r in requests]
    missing = complete(run, seqs)
    if missing and not partial:
        raise SystemExit("the key opens only after every arm has run every change:\n" + "\n".join(missing))
    key, binding = load_sealed(instruments)
    probes = {p["id"]: p for p in yaml.safe_load((instruments / "probe-suite.yaml").read_text())["probes"]}
    rulings = load_rulings(run)
    out = run / "scoring"
    tr, items = out / "transcripts", out / "items"
    work: list[tuple[str, str, int, Any]] = []                  # (arm, kind, seq, job)
    for arm in ARMS:
        for seq, rec in sorted(records(run, arm).items()):
            if seq > 0:
                work.append((arm, "change", seq, lambda a=arm, r=rec: _rematch(a, _cached(
                    items / f"{a}-seq-{r['seq']:02d}-change.json", lambda: grade_change(backend, a, r, key, binding, tr)),
                    binding)))
            for res in rec.get("probes") or []:
                d = run / arm / f"seq-{seq:02d}"

                def job(a=arm, s=seq, res=res, d=d):
                    g = _cached(items / f"{a}-seq-{s:02d}-{res['probe']}.json", lambda: grade_probe(
                        backend, probes[res["probe"]], d, res, tr / f"{a}-seq-{s:02d}-{res['probe']}.jsonl",
                        rulings.get(res["probe"])))
                    m = mechanical(res["probe"], d, res)
                    # the researcher looks first where the two disagree, or the grader could not decide
                    return {"seq": s, **g, "mechanical": m,
                            "look": g["passed"] is None or (m["verdict"] is False and g["passed"] is True)}
                work.append((arm, "probe", seq, job))
    done = [0]

    def run_one(w):
        r = w[3]()
        done[0] += 1
        if backend.progress:
            backend.progress(f"graded {done[0]}/{len(work)}")
        return w, r
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(run_one, work))
    proposal: dict[str, Any] = {"status": "proposed", "partial": bool(missing), "missing": missing, "arms": {
        arm: {"changes": [r for w, r in results if w[0] == arm and w[1] == "change"],
              "probes": [r for w, r in results if w[0] == arm and w[1] == "probe"]} for arm in ARMS}}
    looks = sum(p["look"] for a in proposal["arms"].values() for p in a["probes"])
    proposal["to_look_at_first"] = {
        "seeded_labels": sum(f["label"] == "seeded" for a in proposal["arms"].values() for c in a["changes"]
                             for f in c["findings"]),
        "probes_flagged": looks}
    out.mkdir(parents=True, exist_ok=True)
    path = out / "proposed.yaml"
    path.write_text("# Proposed by the grader (ADR-0040 §8). Review every label, change what is wrong, set\n"
                    "# `status: confirmed`, and save as confirmed.yaml; `score` reads only that file.\n"
                    "# Look first at the findings labelled `seeded` and at the probes with `look: true` (the\n"
                    "# mechanical cross-check disagrees with the grader, or the grader could not decide).\n"
                    + yaml.safe_dump(proposal, sort_keys=False, allow_unicode=True, width=110))
    return path


# -- metrics and verdicts --------------------------------------------------------------------------------

def _seeded(key: dict[int, Any], binding: dict[int, Any]) -> list[int]:
    return [s for s, k in sorted(key.items()) if k.get("problem") not in (None, "none")
            and not (binding.get(s) or {}).get("unbindable")]


def _unique(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for f in findings:
        k = json.dumps(f.get("finding"), sort_keys=True, ensure_ascii=False)
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def arm_metrics(arm: str, graded: dict[str, Any], recs: dict[int, Any], key, binding) -> dict[str, Any]:
    changes = {c["seq"]: c for c in graded["changes"]}
    seeded = _seeded(key, binding)
    flagged = {s for s in seeded if any(f["label"] == "seeded" for f in changes.get(s, {}).get("findings", []))}
    # a check can report the same problem twice (the same element, two samples): count it once
    all_findings = [f for c in changes.values() for f in _unique(c["findings"])]
    real = [f for f in all_findings if f["label"] in ("seeded", "other-real")]

    def recall(of: list[int]) -> float | None:
        return round(len([s for s in of if s in flagged]) / len(of), 4) if of else None

    no_handoff = [s for s in seeded if not handoff_breaking(binding.get(s, {}))]
    by_type: dict[str, list[int]] = {}
    for s in seeded:
        by_type.setdefault(str(key[s].get("type") or "unknown"), []).append(s)
    by_design: dict[str, list[int]] = {}
    for s in seeded:
        by_design.setdefault(str(key[s].get("designed_for_checks", "unknown")), []).append(s)
    # found after deploy: a probe that passed before the change and fails after it
    probe_at: dict[int, dict[str, bool | None]] = {}
    for p in graded["probes"]:
        probe_at.setdefault(p["seq"], {})[p["probe"]] = p["passed"]
    missed = [s for s in seeded if s not in flagged]
    # A probe that turns from pass to fail after change t points at the missed seeded changes
    # deployed since it last failed (or since the start): the problem may surface a change later.
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
    times = [r["seconds"]["edit_to_checked"] for s, r in recs.items() if s > 0 and "edit_to_checked" in r["seconds"]]
    out: dict[str, Any] = {
        "seeded": len(seeded), "flagged": sorted(flagged),
        "recall": recall(seeded), "recall_without_handoff": recall(no_handoff),
        "recall_by_type": {t: recall(v) for t, v in sorted(by_type.items())},
        "recall_by_designed_for_checks": {t: recall(v) for t, v in sorted(by_design.items())},
        "findings": len(all_findings), "precision": round(len(real) / len(all_findings), 4) if all_findings else None,
        "found_after_deploy": after_deploy, "silent": sorted(s for s in missed if s not in after_deploy),
        "breakages_found_only_after_deploy": round(len([s for s in breakages if s in after_deploy]) / len(breakages), 4)
        if breakages else None,
        "median_edit_to_checked_s": round(statistics.median(times), 2) if times else None,
        "edit_fidelity": {f: len([c for c in changes.values() if c["edit"]["fidelity"] == f]) for f in FIDELITY},
        "probes_failed": {s: sorted(pid for pid, ok in v.items() if ok is False) for s, v in sorted(probe_at.items())},
        "handoff_probe_P07_passes_throughout": all(v.get("P07") is True for s, v in probe_at.items() if s > 0)
        if probe_at else None,
    }
    if arm == "toprope":
        out["undeployable"] = sorted(s for s, r in recs.items() if s > 0 and r.get("deploy", {}).get("domains")
                                     and not r["deploy"].get("deployed"))
        out["handoff_breaking_caught"] = {s: s in flagged for s in seeded if handoff_breaking(binding.get(s, {}))}
    return out


def verdicts(m: dict[str, dict[str, Any]], rules: dict[str, Any]) -> dict[str, Any]:
    """The frozen pilot rules (verdict-rules.yaml), applied to the three arms' numbers."""
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
    return {"iterate": iterate, "handoff": handoff,
            "not_measured_here": ["hand_edits_to_generated_max (the self-compile result, reported separately)"],
            "numbers": {"recall": r, "gap_nl": round(gap_nl, 4), "gap_structured": round(gap_st, 4),
                        "toprope_precision": t["precision"], "median_edit_to_checked_s": t["median_edit_to_checked_s"]},
            "note": "M1 pilot targets (ADR-0034): reported, not a link verdict; the claim-status table does not change"}


def score(run: Path, instruments: Path) -> dict[str, Any]:
    conf = run / "scoring/confirmed.yaml"
    if not conf.exists():
        raise SystemExit(f"no {conf}: the researcher confirms the grader's labels first (see proposed.yaml)")
    graded = yaml.safe_load(conf.read_text())
    if graded.get("status") != "confirmed":
        raise SystemExit(f"{conf}: set `status: confirmed` once every label is reviewed")
    unlabelled = [(a, c["seq"], f["index"]) for a, g in graded["arms"].items() for c in g["changes"]
                  for f in c["findings"] if f.get("label") not in LABELS]
    unlabelled += [(a, p["seq"], p["probe"]) for a, g in graded["arms"].items() for p in g["probes"]
                   if not isinstance(p.get("passed"), bool)]
    if unlabelled:
        raise SystemExit(f"{len(unlabelled)} item(s) still have no label, e.g. {unlabelled[:5]}")
    key, binding = load_sealed(instruments)
    rules = yaml.safe_load((instruments / "verdict-rules.yaml").read_text())
    m = {arm: arm_metrics(arm, graded["arms"][arm], records(run, arm), key, binding) for arm in ARMS}
    result = {"partial": graded.get("partial", False), "metrics": m, "verdicts": verdicts(m, rules),
              "unbindable": sorted(s for s, b in binding.items() if b.get("unbindable"))}
    (run / "scoring/metrics.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result
