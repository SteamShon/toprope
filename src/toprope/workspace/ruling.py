"""Choices where the rules are decided (ADR-0053 §2).

The interview's questions about who may take an action, what must be true first, and which
outcome needs whom offer choices built from the draft, and recommend one of them with the reason:
the owner's own words (a source passage, an earlier answer, the glossary) or an example they gave.
Nothing is assumed beyond those: where they say nothing, the recommendation says so, or refuses
(fail-closed) where a refusal is the safe default. Every choice only proposes; a person confirms.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..decl.words import a_, normal, one_line, term

STOP = {"a", "an", "the", "of", "to", "for", "and", "or", "it", "its", "is", "be", "on", "in", "by", "with",
        "their", "they", "them", "this", "that", "who", "what", "any", "one", "each", "every", "not", "no",
        "from", "at", "as", "may", "can", "must", "only", "just", "all", "do", "does"}
# Verbs that let a thing go ahead: their rules guard who and how much (approve, pay, grant...).
ALLOWING = {"approv", "accept", "grant", "authoriz", "authoris", "sign", "pay", "refund", "releas", "decid"}
REFUSING = {"reject", "deni", "deny", "refus", "declin", "cancel", "withdraw"}
OWN_CUES = ("their own", "themselves", "his own", "her own", "your own", "same person", "who asked",
            "who created", "who submitted", "who made")
HUMAN_CUES = ("a person", "human", "not an agent", "never an agent", "no agent", "by hand", "in person")
OVER = re.compile(r"\b(?:over|more than|above|exceeds?|exceeding|greater than|beyond)\s+(\d+(?:[.,]\d+)?)",
                  re.IGNORECASE)


def stem(word: str) -> str:
    """A crude stem, enough to see that `approves`, `approved` and `approve` are one verb."""
    w = re.sub(r"[^a-z]", "", word.lower())
    for suf in ("ing", "ed", "es", "s", "e"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiou":        # submitt → submit
        w = w[:-1]
    return w


def words(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[A-Za-z]+", normal(text)) if w.lower() not in STOP and len(w) > 1}


@dataclass(frozen=True)
class Passage:
    ref: str
    text: str          # one sentence of the owner's words or of a source


def passages(ws: Any) -> list[Passage]:
    """Every sentence the recommendations may cite: the sources a model may read, and the owner's
    answers in the interview log (never the questions asked)."""
    from . import _answer_of
    out: list[Passage] = []
    for spec in ws.sources.values():
        if spec.local_only:
            continue
        try:
            chunks = ws.chunks(spec.id)
        except Exception:  # noqa: BLE001 - an unreadable source gives no evidence
            continue
        for c in chunks:
            text = (_answer_of(c.text) if spec.kind == "interview-log" else c.text) or ""
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
                sentence = one_line(sentence.lstrip("#-* "))
                if sentence:
                    out.append(Passage(c.ref, sentence))
    return out


def verbs(name: str, a: Any) -> set[str]:
    desc = one_line(getattr(a, "description", None) or (a.get("description") if isinstance(a, dict) else "") or "")
    first = desc.split(" ", 1)[0] if desc else ""
    return {stem(x) for x in (first, name.split("_", 1)[0]) if x}


def allowing(name: str, a: Any) -> bool:
    v = verbs(name, a)
    if v & REFUSING:
        return False
    return bool(v & ALLOWING) or bool(getattr(a, "records_decision", False))


def _quote(p: Passage) -> str:
    return f"“{p.text}” ({p.ref})"


def mentions(p: Passage, cues: tuple[str, ...]) -> bool:
    t = f" {p.text.lower()} "
    return any(c in t for c in cues)


def about(ps: list[Passage], stems: set[str]) -> list[Passage]:
    return [p for p in ps if words(p.text) & stems]


def roles_in(p: Passage, roles: list[str]) -> list[str]:
    """The roles a passage names, leaving out the ones it rules out (“not just a manager”)."""
    t = re.sub(r"\bnot (?:just |only |merely |even )?(?:by )?(?:a |an |the )?\w+", " ", normal(p.text))
    return [r for r in roles if re.search(rf"(?<!\w){re.escape(normal(r))}(?!\w)", t)]


# -- who may take an action -------------------------------------------------------------------
def recommend_actor(d: Any, name: str, info: dict[str, Any], asked_role: str | None) -> tuple[list[str], str]:
    """The roles to recommend for a named action, and why; ([], why) when nothing points to one."""
    desc = one_line(info.get("description") or name)
    if asked_role and asked_role in d.roles:
        return [asked_role], f"you named it when asked what the {term(d, asked_role)} does"
    acting = words(f"{desc} {name}")
    scored: dict[str, tuple[int, str]] = {}
    for r in d.roles:
        definition = d.glossary.get(term(d, r)) or d.glossary.get(r) or ""
        if stem(r) in acting or normal(r) in normal(desc):
            scored[r] = (10, f"“{desc}” names the {term(d, r)}")
            continue
        common = sorted(acting & words(f"{r} {definition}"))
        if common and definition:
            scored[r] = (len(common), f"the glossary says the {term(d, r)} “{one_line(definition)}”, as "
                                      f"“{desc}” says ({', '.join(common)})")
    if not scored:
        return [], ""
    best = max(s for s, _ in scored.values())
    top = [r for r in d.roles if r in scored and scored[r][0] == best]
    return top, "; ".join(scored[r][1] for r in top)


# -- what must be true first ------------------------------------------------------------------
def creator(d: Any, obj: str) -> tuple[str, str | None] | None:
    """The fact that records who made a thing, and the action that must start recording it (None
    when some action already records it); None when no action makes the thing."""
    props = d.objects[obj].properties if obj in d.objects else {}
    for p in props:
        if not p.endswith("_by"):
            continue
        for a in d.actions.values():
            for eff in a.effects:
                for k, v in (eff.set or {}).items():
                    if k.split(".", 1)[-1] == p and isinstance(v, str) and "actor." in v:
                        return p, None
    make = [n for n, a in d.actions.items() if a.creates == obj]
    if make:
        return "created_by", make[0]
    return None


def fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def thresholds(d: Any, obj: str, prop: str, ps: list[Passage]) -> list[tuple[float, str, Passage | None, list[str]]]:
    """Candidate limits for a numeric fact: numbers the sources state about it ("over 10 days"),
    then the largest example value. Each with where it came from and the roles its passage names."""
    out: list[tuple[float, str, Passage | None, list[str]]] = []
    names = words(f"{prop} {term(d, prop)}")
    for p in ps:
        if not (words(p.text) & names):
            continue
        for m in OVER.finditer(p.text):
            v = float(m.group(1).replace(",", "."))
            if all(v != x[0] for x in out):
                out.append((v, f"your words say {_quote(p)}", p, roles_in(p, d.roles)))
    best = None
    for f in d.world.fixtures:
        data = f.get(obj) if isinstance(f, dict) else None
        v = (data or {}).get(prop)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and (best is None or v > best[0]):
            best = (float(v), str(data.get("id")))
    if best and all(best[0] != x[0] for x in out):
        out.append((best[0], f"{best[1]} has {term(d, prop)} {fmt(best[0])}, the largest example you gave: above what "
                    "you have seen is refused until you decide otherwise (fail-closed)", None, []))
    return out


__all__ = ["ALLOWING", "HUMAN_CUES", "OWN_CUES", "Passage", "a_", "about", "allowing", "creator", "fmt",
           "mentions", "passages", "recommend_actor", "roles_in", "stem", "thresholds", "verbs", "words"]
