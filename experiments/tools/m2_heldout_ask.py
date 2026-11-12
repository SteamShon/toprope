"""`m2_heldout.py ask`: write M2's held-out items by answering fixed questions at a terminal.

No model is involved. The questions are fixed for every domain, so they shape no content (a
format change, requested by the researcher on 2026-11-12). The answers go only to the file outside
the repository, item by item, so a session can stop and resume. It runs only at a terminal, so an
agent cannot drive it. The guide's examples come from a bakery, on purpose: they show the form,
never the researcher's rules.

Two ways in, which can be mixed:
- Ask (proposal 1): one rule at a time, typed in your own words.
- From notes (proposal 2): write your rules first, one per line, in a text file (`notes` makes one
  with its guide). `ask --from` then walks them one by one, skips the ones already turned into
  items, and asks only what each needs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import sys
from pathlib import Path
from typing import Callable

import yaml

GUIDE = """\
== 무엇에 대해 쓰나 ==
당신(오너)이 지키는 규칙 중, 선언으로 표현할 수 있는 것. 떠올리기 어렵다면 아래 질문으로 기억을 더듬으세요.
  1. 에이전트(또는 다른 사람)가 내 승인 없이 하면 안 되는 일은?
  2. 숫자로 정한 한도나 기준은? (얼마까지, 몇 번까지, 몇 % 이하)
  3. 순서나 시점 조건은? (무엇을 하기 전에 반드시 무엇을, 언제는 하지 않는다)
  4. 예외는? (평소엔 안 되지만 이런 경우엔 된다, 그때 누가 허락하나)
  5. 되돌리는 일은? (취소, 정정, 중단: 누가, 언제까지)
  6. 어떤 일이 끝나면 무엇이 어떤 상태가 되나?
  7. 어떤 경우에도 깨지면 안 되는 것은?
특히 좋은 것: "당연히 이렇게 하지" 싶은데 어디에도 적어 둔 적 없는 규칙.
넣지 않을 것: 시장이나 대상에 관한 사실, 무엇을 고를지에 대한 판단, 도구가 어디서나 보장하는 일.

== 답은 어떤 형태로 ==
규칙 하나를 평소 말투로 한 문장, 그리고 그 규칙을 확인할 형태 하나:
  1) 허용/거부  상황 한 문장 → 허용인지 거부인지 → 이유      (가장 권장: 채점이 기계적)
  2) 예/아니오  예/아니오로 답할 질문 → 예 또는 아니오
  3) 누가       어떤 행동 → 그 행동을 할 수 있는 사람이나 역할들 (쉼표로)
  4) 결과 상태  어떤 일 → 그 뒤의 상태 한 단어나 짧은 구
  5) 서술       질문 → 답에 꼭 들어가야 할 요점들 (사람이 채점: 꼭 필요할 때만)
한 항목에 규칙 하나. 숫자는 숫자 그대로.

== 예시 (빵집, 형식만 보세요) ==
  규칙: 웨딩 케이크는 점장이 확인해야 받는다
  1) 상황: 점원이 혼자 웨딩 케이크 주문을 받으려 한다 → 거부 → 점장 확인 필요
  3) 행동: 웨딩 케이크 주문 받기 → 점장
  4) 일: 시식이 끝난 웨딩 케이크 주문 → 제작 대기
"""

NOTES_GUIDE = """\
# 내 규칙 메모 (M2 held-out 항목의 재료). 저장소 밖에 두세요. 에이전트에게 보여 주지 마세요.
# 한 줄에 규칙 하나, 평소 말투로. 숫자는 숫자 그대로. 예외는 따로 한 줄.
# '#'로 시작하는 줄은 메모로 보고 건너뜁니다. 빈 줄도 건너뜁니다.
# 에이전트의 후보 목록에서 고른 규칙은 줄 앞에 [from-list]를 붙이세요 (ADR-0056): 묻지 않고 tacit false, 꼬리표 from-list.
# 떠올리기: 승인 없이 하면 안 되는 일 / 숫자 한도 / 순서·시점 / 예외 / 취소·정정 / 끝난 뒤 상태 / 절대 깨지면 안 되는 것
# 예시(빵집, 형식만): 웨딩 케이크는 점장이 확인해야 받는다
#                    주문 취소는 픽업 48시간 전까지만 된다
"""

KINDS = {"1": "outcome", "2": "yes_no", "3": "actors", "4": "state", "5": "free_text"}


FROM_LIST = "from-list"


def from_list(rule: str) -> bool:
    """A memo line marked `[from-list ...]` came from an agent's list of candidates (ADR-0056)."""
    return rule.lstrip().startswith(f"[{FROM_LIST}")


def rule_key(rule: str) -> str:
    return hashlib.sha256(" ".join(rule.split()).encode()).hexdigest()[:16]


class Asker:
    def __init__(self, path: Path, ask: Callable[[str], str] = input, say: Callable[[str], None] = print):
        self.path, self.ask, self.say = path, ask, say
        self.doc = yaml.safe_load(path.read_text()) if path.exists() else None
        if not self.doc:
            self.doc = {"instrument": "heldout", "experiment": "M2", "status": "draft", "domain": "", "items": []}
        self.doc.setdefault("items", [])
        self.doc["items"] = [i for i in self.doc["items"] if not str(i.get("question", "")).startswith("<")]

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(self.doc, allow_unicode=True, sort_keys=False))
        tmp.replace(self.path)

    def line(self, prompt: str, allow_empty: bool = False) -> str:
        while True:
            v = self.ask(prompt).strip()
            if v.lower() in ("q", "quit"):
                raise KeyboardInterrupt
            if v or allow_empty:
                return v
            self.say("  (비어 있습니다. 다시 입력하거나 q로 끝내세요)")

    def choice(self, prompt: str, options: str) -> str:
        while True:
            v = self.line(prompt)
            if v in options:
                return v
            self.say(f"  ({', '.join(options)} 중 하나)")

    def item(self, rule: str) -> dict | None:
        """Ask what one rule needs; None when the person skips it."""
        self.say("확인할 형태: 1) 허용/거부  2) 예/아니오  3) 누가  4) 결과 상태  5) 서술   (s: 이 규칙 건너뛰기)")
        k = self.choice("> ", "12345s")
        if k == "s":
            return None
        kind = KINDS[k]
        if kind == "outcome":
            sit = self.line("이 규칙이 걸리는 상황을 한 문장으로: ")
            res = {"a": "allowed", "d": "denied"}[self.choice("그 상황에서?  a) 허용  d) 거부: ", "ad")]
            why = self.line("이유 (짧게, 비워도 됨): ", allow_empty=True)
            q, ans = f"상황: {sit} → 허용되나, 거부되나?", {"kind": kind, "expected": {"result": res, **({"reason": why} if why else {})}}
        elif kind == "yes_no":
            q = self.line("예/아니오로 답할 질문: ")
            ans = {"kind": kind, "expected": {"y": "yes", "n": "no"}[self.choice("정답?  y) 예  n) 아니오: ", "yn")]}
        elif kind == "actors":
            act = self.line("어떤 행동? (예: 웨딩 케이크 주문 받기): ")
            who = [w.strip() for w in self.line("할 수 있는 사람·역할 (쉼표로): ").split(",") if w.strip()]
            q, ans = f"누가 '{act}'을(를) 할 수 있나?", {"kind": kind, "expected": who}
        elif kind == "state":
            ev = self.line("어떤 일이 일어난 뒤? (예: 시식이 끝난 웨딩 케이크 주문): ")
            q, ans = f"{ev} — 그 뒤의 상태는?", {"kind": kind, "expected": self.line("그 상태: ")}
        else:
            q = self.line("질문: ")
            pts = [p.strip() for p in self.line("꼭 들어가야 할 요점 (쉼표로): ").split(",") if p.strip()]
            ans = {"kind": kind, "rubric": pts}
        if from_list(rule):
            # ADR-0056: it came from an agent's list, so it is written down and tagged; not asked.
            tacit, covers = False, [FROM_LIST]
            self.say(f"목록에서 온 규칙: tacit false, 꼬리표 {FROM_LIST} (ADR-0056).")
        else:
            tacit = self.choice("이 규칙, 에이전트가 읽을 수 있는 곳에 적어 둔 적 있나요?  y) 있음  n) 없음: ", "yn") == "n"
            covers = [c.strip() for c in self.line("꼬리표 (선택, 쉼표로, 비워도 됨): ", allow_empty=True).split(",") if c.strip()]
        return {"question": q, "answer": ans, "tacit": tacit, "covers": covers, "rule": rule, "rule_key": rule_key(rule)}

    def add(self, it: dict) -> str:
        used = {str(i.get("id")) for i in self.doc["items"]}
        n = len(self.doc["items"]) + 1
        while f"H{n:02}" in used:
            n += 1
        iid = f"H{n:02}"
        self.doc["items"].append({"id": iid, **it, "notes": ""})
        self.save()
        return iid

    def run_rows(self, rows: list[dict], memo: int, unjudged: int = 0) -> int:
        """A CSV memo: each row with a situation is an item as written; nothing is asked."""
        if not self.doc.get("domain"):
            self.doc["domain"] = self.line("도메인 이름 (인터뷰에서 붙일 이름, 모르면 아무거나): ")
            self.save()
        done = {i.get("rule_key") for i in self.doc["items"]}
        todo = []
        for r in rows:
            if r["rule_key"] not in done:
                done.add(r["rule_key"])
                todo.append(r)
        for r in todo:
            self.add(r)
        self.say(f"CSV의 항목 {len(rows)}개 중 {len(rows) - len(todo)}개는 이미 있고, {len(todo)}개를 넣었습니다. "
                 f"{memo}줄은 상황이 없어 메모로 두었습니다. {unjudged}줄은 판정이 없어(빈칸 또는 모름) 뺐습니다.")
        self.say(f"모두 {len(self.doc['items'])}개. 다 되면 validate, 그 다음 seal.")
        return len(todo)

    def run(self, rules: list[str] | None = None) -> int:
        if not self.doc.get("domain"):
            self.doc["domain"] = self.line("도메인 이름 (인터뷰에서 붙일 이름, 모르면 아무거나): ")
            self.save()
        done = {i.get("rule_key") for i in self.doc["items"]}
        added = 0
        try:
            if rules is not None:
                todo = [r for r in rules if rule_key(r) not in done]
                self.say(f"메모의 규칙 {len(rules)}개 중 {len(rules) - len(todo)}개는 이미 항목입니다. 남은 {len(todo)}개를 묻습니다.")
                for r in todo:
                    self.say(f"\n[{len(self.doc['items']) + 1}번째 항목] 규칙: {r}")
                    it = self.item(r)
                    if it:
                        self.say(f"저장했습니다 ({self.add(it)}).")
                        added += 1
            else:
                while True:
                    self.say(f"\n[{len(self.doc['items']) + 1}번째 항목]")
                    rule = self.line("규칙 하나를 평소 말투로 (q: 끝내기): ")
                    it = self.item(rule)
                    if it:
                        self.say(f"저장했습니다 ({self.add(it)}).")
                        added += 1
                    if self.choice("계속할까요?  y/n: ", "yn") == "n":
                        break
        except (KeyboardInterrupt, EOFError):
            self.say("\n멈췄습니다. 저장된 항목은 그대로 있습니다; 같은 명령으로 이어서 하세요.")
        self.say(f"이번에 {added}개, 모두 {len(self.doc['items'])}개. 다 되면 validate, 그 다음 seal.")
        return added


CSV_COLUMNS = ["규칙", "상황", "결과", "이유", "출처"]
RESULTS = {"거부": "denied", "허용": "allowed"}
UNJUDGED = {"", "모름"}
BLIND = "blind-situation"


def read_csv(path: Path) -> tuple[list[dict], int, int]:
    """A memo saved as CSV: (the rows that are items, rows left as memo, rows not judged).

    Columns 규칙, 상황, 결과 (거부 or 허용), 이유 (optional), 출처 (`from-list` for a rule picked from
    an agent's list, ADR-0056; `blind-situation` for a situation drafted by an agent that never saw
    the rules, ADR-0057). A row without a situation stays memo; a row whose 결과 is empty or 모름
    is left out. Errors name the row, never its content.
    """
    try:
        text = path.expanduser().read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise SystemExit(f"error: {path} is not UTF-8. Fix: save it again as CSV UTF-8 "
                         "(Excel: CSV UTF-8; Numbers: Export to CSV, Unicode UTF-8)") from None
    with io.StringIO(text, newline="") as f:
        reader = csv.DictReader(f)
        if [c.strip() for c in (reader.fieldnames or [])][: len(CSV_COLUMNS)] != CSV_COLUMNS:
            raise SystemExit(f"error: {path}: the first row is not the header. "
                             f"Fix: make the first row {','.join(CSV_COLUMNS)}")
        items, memo, unjudged = [], 0, 0
        for n, row in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            rule, sit = row["규칙"], row["상황"]
            if not rule:
                continue
            if not sit:
                memo += 1
                continue
            if row["결과"] in UNJUDGED:
                unjudged += 1
                continue
            if row["결과"] not in RESULTS:
                raise SystemExit(f"error: {path}: row {n}: 결과 is not 거부, 허용 or 모름. Fix: write 거부, 허용 or 모름 in 결과")
            listed = row["출처"] == FROM_LIST or from_list(rule)
            covers = [FROM_LIST] if listed else [BLIND] if row["출처"] == BLIND else []
            exp = {"result": RESULTS[row["결과"]], **({"reason": row["이유"]} if row["이유"] else {})}
            items.append({"question": f"상황: {sit} → 허용되나, 거부되나?",
                          "answer": {"kind": "outcome", "expected": exp},
                          "tacit": not listed, "covers": covers,
                          "rule": rule, "rule_key": rule_key(rule)})
        return items, memo, unjudged


def write_csv(notes: Path, out: Path) -> int:
    """The text memo as the CSV to fill: one row per rule, `[from-list ...]` moved to 출처."""
    if out.exists():
        raise SystemExit(f"error: {out} exists. Fix: fill that file, or move it away and run again")
    rows = []
    for rule in read_notes(notes):
        listed = from_list(rule)
        if listed:
            rule = rule[rule.index("]") + 1:].strip() if "]" in rule else rule
        rows.append([rule, "", "", "", FROM_LIST if listed else ""])
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        w.writerows(rows)
    return len(rows)


def read_notes(path: Path) -> list[str]:
    return [ln.strip() for ln in path.expanduser().read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def write_notes(path: Path) -> None:
    if path.exists():
        raise SystemExit(f"error: {path} exists. Fix: add your rules to it, or give another path")
    path.write_text(NOTES_GUIDE)


def at_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
