"""Written rules (`AGENTS.md`, skill files, a handbook in Markdown) → candidate rules and the
contradictions between them (ADR-0049 A1b).

A sentence that binds someone (must, never, only, cannot, do not, always, before) is a candidate,
cited by file and line. Two candidates that say opposite things about the same thing are a
conflict, both places named. Neither is a rule: they are questions for the interview, and an
agent drafts elements from the answers (ADR-0041). Deterministic: no model reads the text.

Several files come in one source through the `tree` reader, as its parts. An imperative with no
binding word ("Keep PRs small") is not read: the interview asks for what the text leaves out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from . import Extraction, Profile

NEGATIVE = r"must\s+not|mustn't|never|no\s+\w+\s+may|nobody\s+may|no\s+one\s+may|cannot|can't|can\s+not|do\s+not|don't|does\s+not|doesn't|may\s+not|shall\s+not|should\s+not|shouldn't"
POSITIVE = r"must|always|shall|should|has\s+to|have\s+to|needs?\s+to|is\s+required\s+to|are\s+required\s+to"
MODAL = re.compile(rf"\b(?P<neg>{NEGATIVE})\b|\b(?P<only>only)\b|\b(?P<pos>{POSITIVE})\b|\b(?P<before>before)\b(?!\s+\d)",
                   re.IGNORECASE)
STOP = frozenset("""
a an the to of in on at by for from with into onto and or but if then than that this these those it
its is are be been being was were do does did not no nor so as any all each every one some your you
their they them we our us he she his her i me my mine yours there here when where which who whom
whose what why how only must never always cannot can't can may might should shall will would has
have had need needs needed required before after also just don't doesn't do not same own other
""".split())  # noqa: SIM905 - a word list reads better as text


@dataclass
class Rule:
    text: str
    where: str
    kind: str                    # "never", "must", "only", "before"
    words: frozenset[str]


def _stem(w: str) -> str:
    w = w.lower().strip("`*_'\"")
    for suf in ("ing", "es", "ed", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _plain(sentence: str) -> str:
    """Bold markers out, outside code spans only (`__init__.py` stays as written)."""
    return "".join(part if part.startswith("`") else re.sub(r"\*\*|(?<!\w)__|__(?!\w)", "", part)
                   for part in re.split(r"(`[^`]*`)", sentence))


def _split(parts: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """One paragraph's lines → its sentences, each with the line it starts on. A code span may
    hold a dot (`docs/STATUS.md`); a sentence ends only at `. ` before a capital, a quote or `."""
    text, lines, at = "", [], 0
    for s, n in parts:
        text += ("" if not text else " ") + s
        lines.append((at, n))
        at = len(text) + 1
    masked = re.sub(r"`[^`]*`", lambda m: "x" * len(m.group(0)), text)
    masked = re.sub(r"\*\*", "  ", masked)
    out, start = [], 0
    for m in [*re.finditer(r"(?<=[.!?])\s+(?=[A-Z`(\"“*])", masked), None]:
        end = m.start() if m else len(text)
        if sentence := _plain(text[start:end]).strip():
            first = start + len(text[start:end]) - len(text[start:end].lstrip())
            out.append((sentence, max(n for off, n in lines if off <= first)))
        start = m.end() if m else end
    return out


def _front_matter_end(lines: list[str]) -> int:
    """Skill front matter: `---`, `key: value` lines, `---`. A thematic break is not it."""
    if not lines or lines[0].strip() != "---":
        return 0
    end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), 0)
    body = [ln for ln in lines[1:end] if ln.strip()]
    return end + 1 if end and body and re.match(r"^[A-Za-z_][\w-]*\s*:", body[0]) else 0


def _sentences(text: str) -> list[tuple[str, int]]:
    """Prose sentences with their line, skipping code (fenced or indented), HTML comments, front
    matter and headings. A table row is one sentence, its cells joined; a quote is read as prose."""
    out: list[tuple[str, int]] = []
    para: list[tuple[str, int]] = []
    fence, comment = "", False
    lines = text.splitlines()
    skip = _front_matter_end(lines)

    def flush() -> None:
        out.extend(_split(para))
        para.clear()

    for n, line in enumerate(lines, 1):
        if n <= skip:
            continue
        s = line.strip()
        if fence:
            if re.match(rf"^{re.escape(fence[0])}{{{len(fence)},}}\s*$", s):
                fence = ""
            continue
        if comment:
            comment = "-->" not in s
            continue
        if m := re.match(r"^(`{3,}|~{3,})", s):
            flush()
            fence = m.group(1)
            continue
        if s.startswith("<!--"):
            flush()
            comment = "-->" not in s
            continue
        if not para and re.match(r"^( {4}|\t)", line) and not re.match(r"^\s*(?:[-*+]|\d+[.)])\s", line):
            continue                                              # an indented code block
        s = re.sub(r"^(?:>\s?)+", "", s).strip()                 # a quote is read as prose
        if re.match(r"^#{1,6}(\s|$)", s) or (s and set(s) <= set("|-: ")):
            flush()
        elif s.startswith("|"):
            flush()
            masked = re.sub(r"`[^`]*`", lambda m: m.group(0).replace("|", "\0"), s)
            cells = [c.strip().replace("\0", "|") for c in masked.strip("|").split("|") if c.strip()]
            if cells:
                out.append((_plain(" — ".join(cells)), n))
        elif not s:
            flush()
        else:
            item = re.match(r"^(?:[-*+]|\d+[.)])\s+", s)
            if item:
                flush()
            para.append((s[item.end():] if item else s, n))
    flush()
    return out


def _rules(text: str, where: str) -> list[Rule]:
    rules = []
    for sentence, line in _sentences(text):
        found = [m for m in MODAL.finditer(sentence)]
        if not found:
            continue
        groups = {k for m in found for k, v in m.groupdict().items() if v}
        kind = "never" if "neg" in groups else "only" if "only" in groups else "must" if "pos" in groups else "before"
        plain = re.sub(r"`([^`]*)`", r"\1", sentence)
        words = frozenset(_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z0-9_/-]*", MODAL.sub(" ", plain))
                          if w.lower() not in STOP and len(w) > 2)
        rules.append(Rule(sentence, f"{where}#L{line}", kind, words))
    return rules


def _contradict(a: Rule, b: Rule, overlap: float) -> bool:
    """Opposite modality about the same thing: most of the shorter one's words are shared."""
    if {a.kind, b.kind} != {"never", "must"} or len(a.words) < 2 or len(b.words) < 2:
        return False
    shared = a.words & b.words
    return len(shared) >= 2 and len(shared) / min(len(a.words), len(b.words)) >= overlap


class RulesExtractor:
    kind = "rules"
    LIMIT = 100                                                   # conflicts listed; the rest are counted

    def extract(self, raw, profile: Profile) -> Extraction:
        out = Extraction()
        docs = raw.parts or [raw]                                 # the tree reader gives one part per file
        rules = [r for d in docs for r in _rules(d.data.decode("utf-8", "replace"), d.ref)
                 if not any(ig.lower() in r.text.lower() for ig in profile.ignore)]
        overlap = float(profile.options.get("overlap", 0.8))
        found = 0
        for a, b in combinations(rules, 2):
            if _contradict(a, b, overlap):
                found += 1
                if found <= self.LIMIT:
                    pos, neg = (a, b) if a.kind == "must" else (b, a)
                    out.conflicts.append(f"{pos.where} says “{pos.text}”, but {neg.where} says “{neg.text}”")
        if found > self.LIMIT:
            out.conflicts.append(f"… and {found - self.LIMIT} more like these: the texts repeat one rule both ways, or "
                                 "set `options: {overlap: 0.9}` in the profile to list fewer")
        for r in rules:
            out.questions.append(f"[{r.kind}] {r.where}: “{r.text}” Which action, rule or role is this, and who "
                                 "enforces it?")
        return out
