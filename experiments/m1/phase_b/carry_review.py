"""Carry a reviewer's finding and edit labels from one grading round to the next.

After the first review of the Phase B grading (#119), the probes were graded again (a clarified
prompt and the researcher's rulings) while the findings and edits kept their grades. This copies
the reviewer's `review` notes, and the labels they changed, onto the new proposal, so the new
`confirmed.yaml` starts from both. A probe run a person judged keeps their verdict (the new grade
stays as `rubric_passed`); the others take the new grade.

  python -m phase_b.carry_review OLD_REVIEWED.yaml NEW_PROPOSED.yaml OUT.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def carry(old: dict[str, Any], new: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    log = []
    for arm, g in new["arms"].items():
        before = {c["seq"]: c for c in old["arms"][arm]["changes"]}
        for c in g["changes"]:
            o = before.get(c["seq"])
            if o is None:
                continue
            olds = {f["index"]: f for f in o["findings"]}
            for f in c["findings"]:
                of = olds.get(f["index"])
                if of and of.get("review"):
                    if of["finding"] != f["finding"]:
                        raise SystemExit(f"{arm} {c['seq']} finding {f['index']}: not the same finding")
                    f["label"], f["review"] = of["label"], of["review"]
                    log.append(f"{arm} change {c['seq']} finding {f['index']}: {of['label']} ({of['review'][:60]})")
            if o["edit"].get("review"):
                c["edit"]["fidelity"], c["edit"]["review"] = o["edit"]["fidelity"], o["edit"]["review"]
                log.append(f"{arm} change {c['seq']} edit: {o['edit']['fidelity']} ({o['edit']['review'][:60]})")
        olds = {(x["seq"], x["probe"]): x for x in old["arms"][arm]["probes"]}
        for pr in g["probes"]:
            o = olds.get((pr["seq"], pr["probe"]))
            if o and o.get("review"):                    # a person judged this run: their verdict stands
                pr["rubric_passed"], pr["passed"], pr["review"] = pr["passed"], o["passed"], o["review"]
                pr["look"] = False
                log.append(f"{arm} change {pr['seq']} {pr['probe']}: {o['passed']} (reviewed)")
    looks = sum(p["look"] for g in new["arms"].values() for p in g["probes"])
    new.setdefault("to_look_at_first", {})["probes_flagged"] = looks
    new["status"] = "reviewed (findings, edits, reviewed probe runs); look at the flagged probes, then confirm"
    return new, log


def main(argv: list[str] | None = None) -> None:
    old_p, new_p, out_p = (Path(a) for a in (argv or sys.argv[1:]))
    out, log = carry(yaml.safe_load(old_p.read_text()), yaml.safe_load(new_p.read_text()))
    out_p.write_text("# Findings and edits: the first review's labels, carried (phase_b.carry_review).\n"
                     "# Probes: graded again with the researcher's rulings; review them, then set\n"
                     "# `status: confirmed`.\n" + yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=110))
    print("\n".join(log))
    print(f"{len(log)} carried")


if __name__ == "__main__":
    main()
