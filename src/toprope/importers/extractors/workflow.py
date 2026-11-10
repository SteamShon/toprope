"""A ticket workflow export (`statuses`, `transitions` with `from`, `to`, `name`) → stages,
actions and the cells it allows; every other cell stays undecided (ADR-0049 A1a)."""
from __future__ import annotations

import json

import yaml

from . import Candidate, Extraction, Profile, a_, snake, stages


class WorkflowExtractor:
    kind = "workflow"

    def extract(self, raw, profile: Profile) -> Extraction:
        text, ref, out = raw.data.decode("utf-8", "replace"), raw.ref, Extraction()
        try:
            doc = json.loads(text)
        except ValueError:
            doc = yaml.safe_load(text) or {}
        obj = profile.object
        statuses = [snake(str(s.get("name") if isinstance(s, dict) else s)) for s in doc.get("statuses") or []]
        if not statuses:
            out.questions.append("The export lists no statuses: which stages does it go through?")
            return out
        out.candidates.append(Candidate(f"objects.{obj}", {"description": f"{a_(obj)[0].upper()}{a_(obj)[1:]} in this workflow.",
                                                           "properties": {"status": {"enum": statuses}}}, f"{ref}#/statuses"))
        stages(out, obj, "status", statuses, f"{ref}#/statuses")
        for i, tr in enumerate(doc.get("transitions") or []):
            source_name = str(tr.get("name") or f"transition_{i}")
            name = snake(profile.name(source_name))
            if source_name in profile.ignore or name in profile.ignore:
                continue
            here = f"{ref}#/transitions/{i}"
            froms = tr.get("from") or []
            froms = [snake(str(f)) for f in (froms if isinstance(froms, list) else [froms])] or statuses
            out.candidates.append(Candidate(f"actions.{name}", {"description": str(tr.get("name") or name),
                                                                "actor": list(profile.roles), "target": obj}, here))
            for st in statuses:
                out.candidates.append(Candidate(f"transitions.{obj}.matrix.{st}.{name}",
                                                {"to": snake(str(tr.get("to")))} if st in froms else "undecided", here))
            out.questions.append(f"Who may move {a_(obj)} with “{tr.get('name')}”?")
        return out

