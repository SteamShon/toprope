"""Written rules (`AGENTS.md`, skill files, a handbook in Markdown) → candidate rules and the
contradictions between them (ADR-0049 A1b).

A sentence that binds someone (must, never, only, cannot, do not, always, before) is a candidate,
cited by file and line. Two candidates that say opposite things about the same thing are a
conflict, both places named. Neither is a rule: they are questions for the interview, and an
agent drafts elements from the answers (ADR-0041). Deterministic: no model reads the text.

Several files come in one source through the `tree` reader, which marks where each file starts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from . import Extraction, Profile

FILE_MARK = re.compile(r"^<!-- toprope:file (.+?) -->$")
NEGATIVE = r"must\s+not|mustn't|never|cannot|can't|can\s+not|do\s+not|don't|does\s+not|doesn't|may\s+not|shall\s+not|should\s+not|shouldn't"
POSITIVE = r"must|always|shall|has\s+to|have\s+to|needs?\s+to|is\s+required\s+to|are\s+required\s+to"
MODAL = re.compile(rf"\b(?P<neg>{NEGATIVE})\b|\b(?P<only>only)\b|\b(?P<pos>{POSITIVE})\b|\b(?P<before>before)\b",
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


def _split(parts: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """One paragraph's lines → its sentences, each with the line it starts on. A code span may
    hold a dot (`docs/STATUS.md`); a sentence ends only at `. ` before a capital, a quote or `."""
    text, lines, at = "", [], 0
    for s, n in parts:
        text += ("" if not text else " ") + s
        lines.append((at, n))
        at = len(text) + 1
    text = re.sub(r"\*\*|__", "", text)
    masked = re.sub(r"`[^`]*`", lambda m: "x" * len(m.group(0)), text)
    out, start = [], 0
    for m in [*re.finditer(r"(?<=[.!?])\s+(?=[A-Z`(\"“])", masked), None]:
        end = m.start() if m else len(text)
        if sentence := text[start:end].strip():
            out.append((sentence, max(n for off, n in lines if off <= start + 1) if lines else 0))
        start = m.end() if m else end
    return out


def _sentences(text: str) -> list[tuple[str, int]]:
    """Prose sentences with their line, skipping code, front matter and headings. A table row is
    one sentence, its cells joined."""
    out: list[tuple[str, int]] = []
    para: list[tuple[str, int]] = []
    fence = False
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":                      # skill front matter
        end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), 0)
        lines = [""] * (end + 1) + lines[end + 1:]

    def flush() -> None:
        out.extend(_split(para))
        para.clear()

    for n, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith(("```", "~~~")):
            flush()
            fence = not fence
        elif fence or s.startswith(("#", "<!--")) or (s and set(s) <= set("|-: ")):
            flush()
        elif s.startswith("|"):
            flush()
            if cells := [c.strip() for c in s.strip("|").split("|") if c.strip()]:
                out.append((re.sub(r"\*\*", "", " — ".join(cells)), n))
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
        m = MODAL.search(sentence)
        if not m:
            continue
        kind = "never" if m.group("neg") else "only" if m.group("only") else "must" if m.group("pos") else "before"
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

    def extract(self, raw, profile: Profile) -> Extraction:
        out = Extraction()
        text = raw.data.decode("utf-8", "replace")
        files: list[tuple[str, list[str]]] = []
        for line in text.splitlines():
            if m := FILE_MARK.match(line.strip()):
                files.append((m.group(1), []))
            elif files:
                files[-1][1].append(line)
        if not files:
            files = [(raw.ref, text.splitlines())]
        rules = [r for name, lines in files for r in _rules("\n".join(lines), name)
                 if not any(ig.lower() in r.text.lower() for ig in profile.ignore)]
        overlap = float(profile.options.get("overlap", 0.6))
        for a, b in combinations(rules, 2):
            if _contradict(a, b, overlap):
                pos, neg = (a, b) if a.kind == "must" else (b, a)
                out.conflicts.append(f"{pos.where} says “{pos.text}”, but {neg.where} says “{neg.text}”")
        for r in rules:
            out.questions.append(f"[{r.kind}] {r.where}: “{r.text}” Which action, rule or role is this, and who "
                                 "enforces it?")
        return out
