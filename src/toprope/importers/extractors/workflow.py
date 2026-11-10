"""A ticket workflow export (`statuses`, `transitions` with `from`, `to`, `name`) → stages,
actions and the cells it allows; every other cell stays undecided (ADR-0049 A1a).

Transitions that share a name (Jira often has two "Close") become one action whose cells are
all of theirs."""
from __future__ import annotations

import json

import yaml

from . import Candidate, Extraction, Profile, a_, ignored, mapping, snake, stages


class WorkflowExtractor:
    kind = "workflow"

    def extract(self, raw, profile: Profile) -> Extraction:
        text, ref, out = raw.data.decode("utf-8", "replace"), raw.ref, Extraction()
        try:
            doc = json.loads(text)
        except ValueError:
            doc = yaml.safe_load(text) or {}
        doc = mapping(doc, ref, "a workflow export")
        obj = profile.object
        statuses = list(dict.fromkeys(snake(str(s.get("name") if isinstance(s, dict) else s))
                                      for s in doc.get("statuses") or []))
        if not statuses:
            out.questions.append("The export lists no statuses: which stages does it go through?")
            return out
        out.candidates.append(Candidate(f"objects.{obj}", {"description": f"{a_(obj)[0].upper()}{a_(obj)[1:]} in this workflow.",
                                                           "properties": {"status": {"enum": statuses}}}, f"{ref}#/statuses"))
        stages(out, obj, "status", statuses, f"{ref}#/statuses")
        moves: dict[str, dict] = {}                               # action -> {ref, label, cells: {from: (to, ref)}}
        for i, tr in enumerate(doc.get("transitions") or []):
            if not isinstance(tr, dict):
                continue
            source_name = str(tr.get("name") or f"transition_{i}")
            name = snake(profile.name(source_name))
            if ignored(profile, source_name, name):
                continue
            here = f"{ref}#/transitions/{i}"
            m = moves.setdefault(name, {"ref": here, "label": source_name, "cells": {}})
            to = snake(str(tr["to"])) if tr.get("to") is not None else None
            if to not in statuses:
                out.questions.append(f"“{source_name}” ({here}) moves to {tr.get('to')!r}, which is not among the "
                                     "statuses: which stage is it?")
                continue
            froms = tr.get("from") or []
            froms = [snake(str(f)) for f in (froms if isinstance(froms, list) else [froms])] or statuses
            for f in froms:
                if f in m["cells"] and m["cells"][f][0] != to:
                    out.conflicts.append(f"“{source_name}” from {f} goes to {m['cells'][f][0]} ({m['cells'][f][1]}) "
                                         f"and to {to} ({here}); kept the first")
                    continue
                m["cells"].setdefault(f, (to, here))
        for name, m in moves.items():
            out.candidates.append(Candidate(f"actions.{name}", {"description": m["label"], "actor": list(profile.roles),
                                                                "target": obj}, m["ref"]))
            for st in statuses:
                cell = m["cells"].get(st)
                out.candidates.append(Candidate(f"transitions.{obj}.matrix.{st}.{name}",
                                                {"to": cell[0]} if cell else "undecided", cell[1] if cell else m["ref"]))
            out.questions.append(f"Who may move {a_(obj)} with “{m['label']}”?")
        return out
