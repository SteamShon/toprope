"""Start a domain from a sentence (ADR-0053, decided 1): `toprope-init "<a sentence>"`.

Deterministic, and no model: the closest template is the one whose keywords (in its
`story.yaml`) the sentence uses most; the thing the workflow is about is the word after "submits",
"files", "creates" and the like, and the template's object and actions are renamed to it; and each
rule phrase it recognises becomes the `toprope-rule` command a person would type:

| Phrase | Rule |
|---|---|
| "over 1,000 needs finance", "more than 5 requires a director" | `threshold` |
| "nobody approves their own", "no one … they submitted" | `no-self-approval` |
| "only a person", "agents cannot approve" | `person-only` |
| "within 30 days" | `window` |

What it made from the sentence is `proposed` until the person confirms it (`toprope-rule
confirm`); what it did not understand, it asks as questions, each with the command that answers it.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from ...errors import fixed
from .rule import (Draft, add_field, add_no_self_approval, add_person_only, add_threshold, add_window,
                   rename)
from .start import NAME, hint, init, templates

SUBMIT = {"submit", "file", "create", "raise", "open", "propose", "send", "make", "request", "record", "write"}
NOT_ROLES = {"nobody", "one", "who", "that", "and", "or", "agent", "agents", "person", "human", "it", "they",
             "team", "people", "anyone", "someone", "only", "cannot", "not", "never", "then", "can", "may",
             "must", "will", "also", "which", "a", "an", "the", "each", "every", "any", "their", "own", "bot",
             "is", "are", "be", "been", "was", "were", "get", "gets", "got", "being", "has", "have", "had", "to",
             "first", "then", "later", "always", "usually", "should", "would", "could", "we", "you", "i", "he", "she"}
FILLER = NOT_ROLES | {"for", "with", "in", "on", "of", "by", "from", "them", "at", "into", "via", "as", "so", "but"}
THRESHOLD = re.compile(
    r"\b(over|above|more than|greater than|exceeding|larger than|at least)\s+[$€£]?\s*(\d[\d,]*(?:\.\d+)?)\b"
    r".*?\b(?:needs?|requires?|must (?:be approved by|have|get|go to))\s+(?:an?\s+|the\s+|one\s+|some\s+)?"
    r"([a-z][a-z_-]*)")
SELF = re.compile(r"\b(nobody|no one|no-one|noone|no person|never)\b.*\b(own|themselves|they (?:submitted|filed|"
                  r"made|created|requested|wrote|proposed|raised))\b")
PERSON = re.compile(r"\bonly (?:a |an )?(?:person|human|people|humans)\b|\b(?:agents?|bots?|ai)\b[^.]*?\b"
                    r"(?:cannot|can't|can not|may not|must not|never)\b")
WINDOW = re.compile(r"\bwithin\s+(\d+)\s+(days?|weeks?)\b")
NOUN = re.compile(r"\b(?:submits?|submitted|files?|filed|raises?|raised|creates?|created|opens?|opened|proposes?|"
                  r"proposed|sends?|sent)\s+(?:a|an|the|their|his|her|new|each)?\s*([a-z][a-z-]{2,})(?:\s+([a-z][a-z-]{2,}))?")


def _stems(word: str) -> set[str]:
    w = word.lower()
    out = {w}
    for suffix, cut in (("ies", 3), ("es", 2), ("s", 1), ("ed", 1), ("ed", 2), ("ed", 3), ("ing", 3), ("ing", 4),
                        ("er", 1), ("er", 2), ("al", 2), ("ion", 3)):
        if w.endswith(suffix) and len(w) - cut >= 3:
            out.add(w[:-cut])
    if w.endswith("ies"):
        out.add(w[:-3] + "y")
    return out


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z-]*", text.lower())


def choose_template(text: str) -> tuple[str, list[str]]:
    """The template whose keywords the text uses most; `approval` (the most general) on a tie."""
    stems = set().union(*(_stems(w) for w in _words(text))) if _words(text) else set()
    best, matched = "approval", []
    for name, story in templates().items():
        hit = sorted(k for k in story.get("keywords") or [] if k in stems)
        if len(hit) > len(matched) or (len(hit) == len(matched) and hit and name == "approval"):
            best, matched = name, hit
    return best, matched


def _singular(w: str) -> str:
    if w.endswith("ies"):
        return w[:-3] + "y"
    return w[:-1] if w.endswith("s") and not w.endswith("ss") else w


def _noun(low: str) -> str | None:
    """What the workflow is about: the word (or two) after "submits", "files" and the like."""
    m = NOUN.search(low)
    if not m:
        return None
    second = m.group(2)
    if second and second not in FILLER and not second.endswith(("ly", "ing")):
        return f"{m.group(1)}-{_singular(second)}"
    return _singular(m.group(1))


def _verb(draft: Draft, obj: str, text: str, skip: set[str] = frozenset()) -> str | None:  # type: ignore[assignment]
    """The first action on `obj` whose verb the text uses."""
    acts = [a for a, x in (draft.raw.get("actions") or {}).items() if (x.get("target") or x.get("creates")) == obj
            and a not in skip]
    for w in _words(text):
        for a in acts:
            if a.split("_")[0] in _stems(w):
                return a
    return None


def _like(draft: Draft, obj: str, verbs: set[str], skip: str | None = None) -> str | None:
    for a, x in (draft.raw.get("actions") or {}).items():
        if (x.get("target") or x.get("creates")) == obj and a != skip and a.split("_")[0] in verbs:
            return a
    return None


def _main_object(draft: Draft) -> str:
    counts: dict[str, int] = {}
    for x in (draft.raw.get("actions") or {}).values():
        o = x.get("target") or x.get("creates")
        counts[o] = counts.get(o, 0) + 1
    return max(counts, key=lambda o: counts[o])


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<=[.!?;])\s+|\n+|;", text) if c.strip(" .;")]


def start_from_prose(text: str, name: str | None, where: Path, template: str | None = None) -> Path:
    tname, matched = (template, []) if template else choose_template(text)
    low = text.lower()
    noun = _noun(low)
    name = name or f"my-{(noun + 's') if noun else tname}"
    if not NAME.match(name):
        raise SystemExit(fixed(f"{name!r} is not a domain name", "give --name, in lowercase letters, digits and dashes"))
    out = init(name, tname, where)
    try:
        said = _draft(out, text, tname, matched, noun)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)            # nothing half-written is left to block a retry
        raise
    print("\n".join(said))
    print(f"\nwrote {out}/: domain.yaml, tokens.yaml, story.yaml, toprope.yaml. This is a draft: check it with\n"
          f"  cd {out}\n  {hint('toprope-try')}\n"
          f"then make the rules yours with `{hint('toprope-rule confirm')}`, or change them with toprope-rule.")
    return out


def _draft(out: Path, text: str, tname: str, matched: list[str], noun: str | None) -> list[str]:
    draft = Draft.open(out)
    head = [f"started from the template {tname}" + (f" (your words matched: {', '.join(matched)})" if matched else
                                                     " (no template matched your words; it is the most general)")]
    obj = _main_object(draft)
    tnoun = re.findall(r"[A-Z][a-z0-9]*", obj)[-1].lower()
    questions: list[str] = []
    understood: set[str] = set()
    if noun and noun != tnoun and noun not in (o.lower() for o in draft.raw["objects"]):
        new_obj = "".join(p.capitalize() for p in noun.split("-"))
        try:
            rename(draft, obj, new_obj, "object")
            obj = new_obj
            for a in list(draft.raw["actions"]):
                if a.endswith(f"_{tnoun}") and draft.obj_of(a) == obj:
                    rename(draft, a, a[: -len(tnoun)] + noun.replace("-", "_"), "action")
            understood |= {c for c in _clauses(text) if NOUN.search(c.lower())}
        except SystemExit as e:
            questions.append(f'I could not name things after "{noun}": {e.code}')
    kept = [(p.get("id"), p.get("reason")) for a in draft.raw["actions"].values() for p in a.get("preconditions") or []]
    kept += [(f"person-only/{n}", f"only a person may {n}") for n, a in draft.raw["actions"].items()
             if a.get("requires") == "human"]
    rules: list[tuple[str, str]] = []
    roles = set(draft.raw.get("roles") or [])
    asked: set[str] = set()
    for clause in _clauses(text):
        low = clause.lower()
        before = len(rules)
        try:
            if t := THRESHOLD.search(low):
                op = ">=" if t.group(1) == "at least" else ">"
                act = _verb(draft, obj, low) or _like(draft, obj, {"approve"})
                nums = [k for k, p in draft.props(obj).items() if p.get("type") in ("integer", "number")]
                if act is None:
                    questions.append(f'"{clause}": which action does it hold back? Add it with '
                                     f'toprope-rule threshold --action ACTION --when "amount {op} {t.group(2)}" --needs {t.group(3)}')
                elif len(nums) > 1:
                    questions.append(f'"{clause}": which number is it about ({", ".join(nums)})? Add it with '
                                     f'toprope-rule threshold --action {act} --when "FIELD {op} {t.group(2)}" --needs {t.group(3)}')
                else:
                    if not nums:
                        by = _like(draft, obj, SUBMIT, act)
                        add_field(draft, "amount", "integer", obj, [by] if by else None, "0")
                        nums = ["amount"]
                    rules.append((add_threshold(draft, act, f"{nums[0]} {op} {t.group(2)}", t.group(3), quote=clause), clause))
            if SELF.search(low):
                act = _verb(draft, obj, low, skip={a for a in draft.raw["actions"] if a.split("_")[0] in SUBMIT}) \
                    or _like(draft, obj, {"approve"})
                if act is None:
                    questions.append(f'"{clause}": which action may nobody take on their own? Add it with '
                                     f"toprope-rule no-self-approval --action ACTION --by ACTION")
                else:
                    rules.append((add_no_self_approval(draft, act, quote=clause) if _has_owner(draft, obj, act) else
                                  add_no_self_approval(draft, act, by=_like(draft, obj, SUBMIT, act), quote=clause), clause))
            if PERSON.search(low):
                act = _verb(draft, obj, low) or _like(draft, obj, {"approve"})
                if act is None:
                    questions.append(f'"{clause}": which action is for a person only? Add it with '
                                     "toprope-rule person-only --action ACTION")
                else:
                    rules.append((add_person_only(draft, act, quote=clause), clause))
            if w := WINDOW.search(low):
                days = int(w.group(1)) * (7 if w.group(2).startswith("week") else 1)
                act = _verb(draft, obj, low) or _like(draft, obj, {"approve"})
                if act is None:
                    questions.append(f'"{clause}": which action has the time limit? Add it with '
                                     f"toprope-rule window --action ACTION --days {days} --since ACTION")
                else:
                    days_fields = [k for k, p in draft.props(obj).items()
                                   if p.get("type") == "integer" and "day" in k or p.get("type") == "datetime"]
                    since = None if len(days_fields) == 1 else _like(draft, obj, SUBMIT, act)
                    rules.append((add_window(draft, act, days, days_fields[0] if since is None and days_fields else None,
                                             since, quote=clause), clause))
        except SystemExit as e:
            questions.append(f'"{clause}": I read a rule in it but could not add it: {e.code}')
        if len(rules) > before or any(clause in q for q in questions):
            understood.add(clause)
        for a in (draft.raw.get("actions") or {}):
            verb = a.split("_")[0]
            for sm in re.finditer(rf"\b([a-z]+)\s+(?:can\s+|may\s+|must\s+|will\s+|also\s+)?({verb}[a-z]*)\b", low):
                who, roles = sm.group(1), set(draft.raw.get("roles") or [])
                if sm.group(2).endswith(("er", "ers")) or verb not in _stems(sm.group(2)):
                    continue                              # "a finance approver" names a role, not who acts
                if who in NOT_ROLES or _singular(who) in roles or who in roles:
                    if _singular(who) in roles or who in roles:
                        understood.add(clause)
                    continue
                if _singular(who) not in asked:
                    asked.add(_singular(who))
                    understood.add(clause)
                    questions.append(
                        f'who is "{_singular(who)}"? The roles are {", ".join(draft.raw.get("roles") or [])}. If it is '
                        f"one of them by another name: toprope-rename ROLE {_singular(who)}; if it is new: "
                        f"toprope-add role {_singular(who)} --may {a}")
    for clause in _clauses(text):
        if clause not in understood:
            questions.append(f'I did not understand "{clause}". If it is a rule, add it with toprope-rule '
                             "threshold | no-self-approval | person-only | window (each has --help)")
    draft.story["title"] = f"A draft from your sentence (template {tname})"
    draft.story["about"] = text
    draft.save()
    lines = head + draft.said
    had = {i for i, _ in kept}
    new = [(rid, c) for rid, c in rules if rid not in had]
    lines.append("\nrules drafted from your sentence (proposed until you confirm them):" if new else
                 "\nno new rule was drafted from your sentence")
    lines += [f'  {rid}  <- "{clause}"' for rid, clause in new]
    same = [(rid, c) for rid, c in rules if rid in had]
    if same:
        lines.append("your sentence says what the template already has:")
        lines += [f'  {rid}  <- "{clause}"' for rid, clause in same]
    mine = {rid for rid, _ in rules}
    left = [(i, r) for i, r in kept if i not in mine]
    if left:
        lines.append("kept from the template, not from your sentence (remove any that is not yours with "
                     "`toprope-rule remove ID`):")
        lines += [f"  {i}: {r}" for i, r in left]
    if questions:
        lines.append("questions:")
        lines += [f"  - {q}" for q in questions]
    return lines


def _has_owner(draft: Draft, obj: str, action: str) -> bool:
    from .rule import _owner_fields
    return bool(_owner_fields(draft, obj, action, None))


__all__ = ["choose_template", "start_from_prose"]
