"""Add your own rules, roles, people and fields to a domain by command, with no YAML (ADR-0053, F2).

    toprope-rule list                                    # the domain's rules, with their ids
    toprope-rule threshold --action approve_request --when "amount > 1000" --needs finance
    toprope-rule no-self-approval --action approve_request
    toprope-rule person-only --action approve_request
    toprope-rule window --action approve_request --days 30 --since submit_request
    toprope-rule remove amount-over-1000-needs-finance
    toprope-rule confirm                                 # a drafted rule (`proposed`) becomes yours

    toprope-add role finance --may approve_request
    toprope-add person fay --roles finance
    toprope-add agent helper --for mia --may submit_request
    toprope-add field amount --type integer --set-by submit_request --default 0

    toprope-rename AccessRequest Claim                   # an object, an action, a role or a field
    toprope-remove field system                          # a template's leftover: refused while still used

What a command changes is written `proposed`, unless the person who typed it confirms it at a
terminal (they are asked to type yes): then it is `confirmed`, theirs. Run by an agent or a script
(no terminal), it stays proposed until a person runs `toprope-rule confirm` in a terminal. This is
a local guard, not authentication: it keeps an agent in a pipeline from making rules a person's by
itself. Proposed or confirmed, a rule is enforced the same way by `toprope-try` and `toprope-run`.
Removing a confirmed rule also takes a person at a terminal.

Each command changes `domain.yaml` (and `tokens.yaml`, `story.yaml` where it must), checks the
result (the declaration validates, the harness finds nothing, the story still runs), and writes
nothing if a check fails. A rule command also adds a step to the story that shows the new rule
refusing, so `toprope-try` demonstrates it; `toprope-rule remove` takes back what was added only
for that. A draft from `toprope-init "<a sentence>"` is always `proposed`.

These commands rewrite the YAML files whole: comments in them are not kept.
"""
from __future__ import annotations

import argparse
import copy
import re
import shlex
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from ...errors import fixed
from .start import ROLE, dump_yaml, hint, load, play, sync_store

EXAMPLE_OWNER = "(an example)"                     # who made an example object, for a no-self-approval rule
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
SNAKE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
OBJECT = re.compile(r"^[A-Z][A-Za-z0-9]{0,40}$")
PERSON = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")
NAMES = ["kim", "jo", "lee", "ray", "ash", "noa", "sky", "rio", "val", "ari"]
TYPES = ("integer", "number", "string", "boolean", "datetime")
WHEN = re.compile(r"^\s*([A-Za-z_]\w*)\s*(>=|<=|==|!=|>|<)\s*(.+?)\s*$")
OPWORD = {">": "over", ">=": "at-least", "<": "under", "<=": "at-most", "==": "is", "!=": "is-not"}


# -- the domain's three files, changed together -------------------------------------------------

@dataclass
class Draft:
    """domain.yaml, tokens.yaml and story.yaml of one directory, changed in memory, then checked
    and written together (or not at all)."""
    where: Path
    raw: dict[str, Any]
    tokens: dict[str, Any]
    story: dict[str, Any]
    said: list[str] = field(default_factory=list)
    quote: str | None = None                              # the command, kept as each changed element's source
    touched: list[dict[str, Any]] = field(default_factory=list)   # elements this change writes or changes
    printed: int = 0
    _texts: dict[str, str] = field(default_factory=dict)

    def touch(self, el: dict[str, Any], quote: str | None = None) -> dict[str, Any]:
        """Mark an element as changed by this command: it is written `proposed` unless a person
        confirms the change at a terminal (`confirmed`). `quote` is where it came from (prose)."""
        if not any(x is el for x in self.touched):
            self.touched.append(el)
        if quote is not None:
            el["source"] = {"kind": "interview", "quote": quote}
        return el

    @classmethod
    def open(cls, where: Path) -> Draft:
        from ...decl import load_yaml
        for f in ("domain.yaml", "tokens.yaml", "story.yaml"):
            if not (where / f).is_file():
                raise SystemExit(fixed(f"no {f} in {where}", "run this in a directory toprope-init wrote, or give --dir"))
        load(where / "domain.yaml")                       # the starting point is valid, or says where not
        texts = {f: (where / f).read_text() for f in ("domain.yaml", "tokens.yaml", "story.yaml")}
        return cls(where, load_yaml(texts["domain.yaml"]), load_yaml(texts["tokens.yaml"]) or {},
                   yaml.safe_load(texts["story.yaml"]) or {}, _texts=texts)

    # reads
    def action(self, name: str) -> dict[str, Any]:
        a = (self.raw.get("actions") or {}).get(name)
        if a is None:
            raise SystemExit(fixed(f"no action {name!r}", f"use one of {', '.join(self.raw.get('actions') or {})}"))
        return a

    def obj_of(self, action: str) -> str:
        a = self.action(action)
        return a.get("target") or a.get("creates")

    def props(self, obj: str) -> dict[str, Any]:
        return self.raw["objects"][obj].setdefault("properties", {})

    def roles_of(self, action: str) -> list[str]:
        return [r if isinstance(r, str) else r.get("role") for r in self.action(action).get("actor") or []]

    def people(self) -> dict[str, dict[str, Any]]:
        return {t: c for t, c in self.tokens.items() if isinstance(c, dict) and c.get("kind", "person") == "person"}

    def agents(self) -> dict[str, dict[str, Any]]:
        return {t: c for t, c in self.tokens.items() if isinstance(c, dict) and c.get("kind") == "agent"}

    def rule_ids(self) -> set[str]:
        return {p.get("id") for a in (self.raw.get("actions") or {}).values() for p in a.get("preconditions") or []}

    def free_name(self) -> str:
        used = {str(c.get("id")) for c in self.tokens.values() if isinstance(c, dict)} | {
            str((c.get("on_behalf_of") or {}).get("id")) for c in self.tokens.values() if isinstance(c, dict)}
        return next(n for n in NAMES + [f"p{i}" for i in range(100)] if n not in used and f"t-{n}" not in self.tokens)

    # changes
    def add_role(self, role: str) -> None:
        if not ROLE.fullmatch(role):
            raise SystemExit(fixed(f"{role!r} is not a role name", "use letters, digits, `_` and `-`"))
        roles = self.raw.setdefault("roles", [])
        if role not in roles:
            roles.append(role)
            self.said.append(f"added the role {role}")

    def let_take(self, role: str, action: str) -> None:
        if role not in self.roles_of(action):
            self.action(action).setdefault("actor", []).append(role)
            self.touch(self.action(action))
            self.said.append(f"{role} may now take {action}")

    def add_person(self, roles: list[str], name: str | None = None, why: str = "") -> str:
        name = name or self.free_name()
        token = f"t-{name}"
        self.tokens[token] = {"id": name, "roles": list(roles)}
        self.said.append(f"added a person {name} ({', '.join(roles)}), token {token}{why}")
        return token

    def label(self, token: str) -> str:
        for st in self.story.get("steps") or []:
            if st.get("who") == token and st.get("as"):
                return st["as"]
        c = self.tokens.get(token) or {}
        return "the agent" if c.get("kind") == "agent" else f"{c.get('id')} ({', '.join(c.get('roles') or [])})"

    def _dump(self) -> dict[str, str]:
        from ...decl import load_yaml
        return {"domain.yaml": dump_yaml(self.raw, "domain.yaml"),
                "tokens.yaml": dump_yaml(self.tokens, "tokens.yaml", load_yaml),
                "story.yaml": dump_yaml(self.story, "story.yaml", yaml.safe_load)}

    def save(self, check_harness: bool = True, confirm: Any = None) -> Any:
        """Check everything, then write the files that changed. Returns the declaration. What this
        command changed is written `proposed`, or `confirmed` when `confirm()` says a person did."""
        from ...decl import load_yaml
        for el in self.touched:
            el["status"] = "proposed"
            if self.quote and "source" not in el:
                el["source"] = {"kind": "interview", "quote": self.quote}
        texts = self._dump()
        with tempfile.TemporaryDirectory() as tmp:
            for f, t in texts.items():
                (Path(tmp) / f).write_text(t)
            d = load(Path(tmp) / "domain.yaml")
            if check_harness:
                from ...harness import run_harness
                r = run_harness(d, levels=("model",), explore_examples=5, races=False)
                if not r.ok:
                    raise SystemExit(fixed(f"the harness finds a problem with this change: {r.summary()}",
                                           "nothing was written; change the command (or undo the hand edit it "
                                           "builds on), then try again"))
            _story_runs(Path(tmp))
        if self.touched and confirm is not None and confirm(self) == "confirmed":
            for el in self.touched:
                el["status"] = "confirmed"
            texts = self._dump()
        changed = {f: t for f, t in texts.items() if load_yaml(t) != load_yaml(self._texts[f])}
        for f, t in changed.items():
            (self.where / f).write_text(t)
            self._texts[f] = t
        if said := sync_store(self.where, d):
            self.said.append(said)
        return d


def _story_runs(where: Path) -> None:
    try:
        play(where)
    except SystemExit as e:
        raise SystemExit(fixed(f"the story would no longer run: {e.code}", "nothing was written; change the "
                               "command so the story's actions and objects stay")) from None


# -- trying a step on a scratch copy -------------------------------------------------------------

def _simulate(raw: dict[str, Any], tokens: dict[str, Any], steps: list[dict[str, Any]],
              at: datetime | None = None) -> list[tuple[bool, str | None]]:
    from ...decl import Domain
    from ...exec import Execution
    from ...store import open_store
    from ..mcp.cli import open_identity
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "t.yaml").write_text(yaml.safe_dump(tokens))
        ex = Execution(Domain.model_validate(raw), open_store("memory"), open_identity(f"static:{Path(tmp) / 't.yaml'}"))
    ex.seed_world()
    out = []
    for st in steps:
        o = ex.submit(st["who"], st["action"], st["target"], dict(st.get("params") or {}),
                      idempotency_key=str(uuid.uuid4()))
        out.append((o.ok, o.code))
    return out


def _sample(p: dict[str, Any]) -> Any:
    if p.get("enum"):
        return p["enum"][0]
    return {"integer": 1, "number": 1, "boolean": True, "string": "x",
            "datetime": datetime.now(timezone.utc).isoformat()}.get(p.get("type"))


def _params(draft: Draft, action: str) -> dict[str, Any] | None:
    out = {}
    for name, p in (draft.action(action).get("params") or {}).items():
        if p.get("optional"):
            continue
        v = _sample(p)
        if v is None:
            return None                                   # a reference: no example to give
        out[name] = v
    return out


def _moves(draft: Draft, obj: str, state: str | None, action: str) -> bool:
    tr = (draft.raw.get("transitions") or {}).get(obj)
    if tr is None:
        return True
    c = (tr.get("matrix") or {}).get(state, {}).get(action)
    return isinstance(c, str) and c not in ("n/a", "undecided") or isinstance(c, dict) and ("to" in c or "by_role" in c)


def _states(draft: Draft, obj: str) -> tuple[str | None, list[str | None]]:
    tr = (draft.raw.get("transitions") or {}).get(obj)
    return (None, [None]) if tr is None else (tr["field"], list((tr.get("matrix") or {}).keys()))


def _fixtures(draft: Draft, obj: str) -> list[dict[str, Any]]:
    return [data for fx in (draft.raw.get("world") or {}).get("fixtures") or [] for o, data in fx.items() if o == obj]


def _new_id(draft: Draft, base: str, rule: str) -> str:
    used = {data.get("id") for fx in (draft.raw.get("world") or {}).get("fixtures") or [] for data in fx.values()}
    stem = f"{base.split('-')[0]}-{rule}"[:60]
    i, oid = 1, stem
    while oid in used:
        i += 1
        oid = f"{stem}-{i}"
    return oid


def show_refusal(draft: Draft, rule: str, code: str, action: str, without: dict[str, Any],
                 who: list[str], set_to: dict[str, Any] | None = None, before: str | None = None,
                 allowed: list[str] | None = None, says: str = "") -> bool:
    """Add an example object and story steps in which `who` takes `action` and is refused with
    `code` because of the new rule: the same steps on the declaration `without` the rule are not
    refused. Tries each example of the object in each state; the first that shows it is kept."""
    obj = draft.obj_of(action)
    field_, states = _states(draft, obj)
    for base in _fixtures(draft, obj) or [{}]:
        for state in states:
            first = before or action
            if not _moves(draft, obj, state, first):
                continue
            fx = {k: v for k, v in copy.deepcopy(base).items()}
            fx["id"] = _new_id(draft, str(base.get("id", obj[0])), _slug(rule))
            if field_:
                fx[field_] = state
            fx.update(set_to or {})
            for token in who:
                steps = []
                if before:
                    p = _params(draft, before)
                    if p is None:
                        continue
                    steps.append({"who": token, "as": draft.label(token), "action": before, "target": fx["id"],
                                  "says": f"{before.replace('_', ' ')} {fx['id']}", "params": p, "expect": "ok"})
                p = _params(draft, action)
                if p is None:
                    continue
                steps.append({"who": token, "as": draft.label(token), "action": action, "target": fx["id"],
                              "says": says or f"{action.replace('_', ' ')} {fx['id']}", "params": p,
                              "expect": "denied", "code": code, "rule": rule})
                with_fx = copy.deepcopy(draft.raw)
                with_fx.setdefault("world", {}).setdefault("fixtures", []).append({obj: fx})
                wo = copy.deepcopy(without)
                wo.setdefault("world", {}).setdefault("fixtures", []).append({obj: fx})
                try:
                    now = _simulate(with_fx, draft.tokens, steps)
                    then = _simulate(wo, draft.tokens, steps)
                except Exception:                         # noqa: BLE001 - this example does not fit; try the next
                    continue
                if not (all(ok for ok, _ in now[:-1]) and now[-1] == (False, code) and then[-1][0]):
                    continue
                extra = []
                for other in allowed or []:              # and someone the rule lets through
                    ok_step = {**steps[-1], "who": other, "as": draft.label(other), "expect": "ok"}
                    ok_step.pop("code")
                    try:
                        if _simulate(with_fx, draft.tokens, steps[:-1] + [ok_step])[-1][0]:
                            extra = [ok_step]
                            break
                    except Exception:                     # noqa: BLE001
                        continue
                draft.raw.setdefault("world", {}).setdefault("fixtures", []).append({obj: fx})   # in place: keep
                demo = draft.story.setdefault("demos", {}).setdefault(rule, {})
                demo.setdefault("fixtures", []).append(fx["id"])
                for st in steps + extra:
                    if not st.get("params"):
                        st.pop("params", None)
                    st.setdefault("rule", rule)
                draft.story.setdefault("steps", []).extend(steps + extra)
                draft.said.append(f"the story now shows it: {draft.label(token)} asks to {steps[-1]['says']} "
                                  f"and is refused ({code})")
                return True
    draft.said.append(f"the story could not show {rule} refusing with the examples there are (it is enforced; "
                      f"try it with {hint('toprope-run')})")
    return False


# -- the rule kinds ------------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")[:60] or "rule"


def _unique_id(draft: Draft, given: str | None, default: str) -> str:
    rid = given or _slug(default)
    if not IDENT.match(rid):
        raise SystemExit(fixed(f"{rid!r} is not a rule id", "use letters, digits, `-` and `_`, starting with a letter"))
    if rid in draft.rule_ids():
        raise SystemExit(fixed(f"there is already a rule {rid!r}", "give another --id, or "
                               f"`toprope-rule remove {rid}` first"))
    return rid


def _demo_tokens(draft: Draft, rule: str, before: set[str]) -> None:
    """Record the tokens a rule command added only to show the rule, so `remove` takes them back."""
    new = [t for t in draft.tokens if t not in before]
    if new:
        draft.story.setdefault("demos", {}).setdefault(rule, {})["tokens"] = new


def _role_check(role: str) -> str:
    """The role, held by the actor and, for an agent, by the person it acts for (ADR-0041,
    Resolved 4: `actor.principal` is the actor itself for a person)."""
    return f"'{role}' in actor.roles and '{role}' in actor.principal.roles"


def _literal(prop: dict[str, Any], name: str, given: str) -> tuple[str, Any]:
    v = given.strip().strip("'\"")
    if prop.get("enum"):
        if v not in prop["enum"]:
            raise SystemExit(fixed(f"{name} is one of {', '.join(prop['enum'])}, not {v!r}", "give one of those"))
        return f"'{v}'", v
    kind = prop.get("type")
    if kind in ("integer", "number"):
        num = v.replace(",", "").replace("_", "")
        try:
            x: Any = int(num) if kind == "integer" else float(num)
        except ValueError:
            raise SystemExit(fixed(f"{name} is a number, not {v!r}", f'give e.g. --when "{name} > 1000"')) from None
        return str(x), x
    if kind == "boolean" and v in ("true", "false"):
        return v, v == "true"
    if kind == "string" and re.fullmatch(r"[\w .:-]{1,80}", v):
        return f"'{v}'", v
    raise SystemExit(fixed(f"{name} ({kind}) cannot be compared with {v!r} in a threshold",
                           "compare a number, a choice (enum) or plain text; for time limits use `toprope-rule window`"))


def _violating(op: str, prop: dict[str, Any], v: Any) -> Any:
    """A value for which `field op v` holds (so the rule applies)."""
    if prop.get("enum"):
        return v if op == "==" else next((x for x in prop["enum"] if x != v), v)
    if isinstance(v, bool):
        return v if op == "==" else not v
    if isinstance(v, (int, float)):
        return {">": v + 1, ">=": v, "<": v - 1, "<=": v, "==": v, "!=": v + 1}[op]
    return v if op == "==" else f"{v}-other"


def add_threshold(draft: Draft, action: str, when: str, needs: str, rid: str | None = None,
                  reason: str | None = None, quote: str | None = None) -> str:
    m = WHEN.match(when)
    if not m:
        raise SystemExit(fixed(f"--when {when!r} is not `field op value`", 'give e.g. --when "amount > 1000"'))
    name, op, value = m.groups()
    obj = draft.obj_of(action)
    props = draft.props(obj)
    if name not in props:
        others = [a for a, x in (draft.raw.get("actions") or {}).items() if (x.get("target") or x.get("creates")) == obj
                  and a != action]
        raise SystemExit(fixed(f"{obj} has no {name} (it has {', '.join(props) or 'no fields'})",
                               f"add it first: toprope-add field {name} --type integer --set-by "
                               f"{others[0] if others else '<the action that records it>'} --default 0"))
    text, v = _literal(props[name], name, value)
    tokens_before = set(draft.tokens)
    draft.add_role(needs)
    draft.let_take(needs, action)
    if not any(needs in (c.get("roles") or []) for c in draft.people().values()):
        draft.add_person([needs], why=", to try it")
    rid = _unique_id(draft, rid, f"{name}-{OPWORD[op]}-{v}-needs-{needs}")
    if f"{rid}-known" in draft.rule_ids():
        raise SystemExit(fixed(f"there is already a rule {rid}-known", "give another --id"))
    who = _role_check(needs)
    pres = []
    if props[name].get("type") in ("integer", "number"):  # no value: the role decides, and the refusal says so
        setters = [a for a, x in (draft.raw.get("actions") or {}).items()
                   for e in x.get("effects") or [] if (e.get("set") or {}).get(f"target.{name}") == f"params.{name}"]
        how = (f"give it when taking {' or '.join(setters)} (--{name})" if setters else
               f"record it first (toprope-add field {name} --set-by ACTION gives an action that records it)")
        pres.append(draft.touch({"id": f"{rid}-known", "check": f"{who} or exists(target.{name})",
                                 "reason": f"This has no {name}, so only {needs} may {action.replace('_', ' ')} it; "
                                           f"{how}."}, quote))
    pre = draft.touch({"id": rid, "check": f"{who} or not (target.{name} {op} {text})",
                       "reason": reason or f"When {name} {op} {v}, only {needs} may {action.replace('_', ' ')}."}, quote)
    pres.append(pre)
    without = copy.deepcopy(draft.raw)
    draft.action(action).setdefault("preconditions", []).extend(pres)
    draft.said.append(f"rule {rid}: {pre['reason']}")
    roles = set(draft.roles_of(action))
    deniers = [t for t, c in draft.people().items() if set(c.get("roles") or []) & roles and needs not in (c.get("roles") or [])]
    allowed = [t for t, c in draft.people().items() if needs in (c.get("roles") or [])]
    if not deniers:
        other = next((r for r in draft.roles_of(action) if r != needs), None)
        if other:
            deniers = [draft.add_person([other], why=", to show the rule refusing")]
    show_refusal(draft, rid, rid, action, without, deniers, {name: _violating(op, props[name], v)}, allowed=allowed,
                 says=f"{action.replace('_', ' ')} one with {name} {_violating(op, props[name], v)}")
    _demo_tokens(draft, rid, tokens_before)
    return rid


def _owner_fields(draft: Draft, obj: str, action: str, by: str | None) -> list[tuple[str, str]]:
    out = []
    for a, x in (draft.raw.get("actions") or {}).items():
        if a == action or (x.get("target") or x.get("creates")) != obj or (by and a != by):
            continue
        for e in x.get("effects") or []:
            for k, v in (e.get("set") or {}).items():
                if k.startswith("target.") and str(v).strip() in ("actor.principal.id", "actor.id"):
                    out.append((a, k.split(".", 1)[1]))
    return out


def add_no_self_approval(draft: Draft, action: str, by: str | None = None, rid: str | None = None,
                         reason: str | None = None, quote: str | None = None) -> str:
    obj = draft.obj_of(action)
    tokens_before = set(draft.tokens)
    if by is not None:
        draft.action(by)
    found = _owner_fields(draft, obj, action, by)
    if not found:
        if by is None:
            cands = [a for a, x in (draft.raw.get("actions") or {}).items()
                     if (x.get("target") or x.get("creates")) == obj and a != action]
            raise SystemExit(fixed(f"nothing records who made a {obj} theirs",
                                   f"give --by ACTION, the action that does (one of {', '.join(cands) or 'none'})"))
        fname = f"{by}_by"
        if fname in draft.props(obj):
            raise SystemExit(fixed(f"{obj} already has a field {fname}", "give another --by, or rename that field"))
        draft.props(obj)[fname] = {"type": "string", "optional": True}
        draft.touch(draft.raw["objects"][obj])
        draft.action(by).setdefault("effects", []).append({"set": {f"target.{fname}": "actor.principal.id"}})
        draft.touch(draft.action(by))
        draft.said.append(f"{by} now records who took it, in {obj}.{fname}")
        found = [(by, fname)]
    by, fname = found[0]
    for p in draft.action(action).get("preconditions") or []:
        if re.sub(r"\s+", "", str(p.get("check"))) == f"target.{fname}!=actor.principal.id":
            draft.said.append(f"already a rule: {p['id']} ({p.get('reason')})")
            return p["id"]
    rid = _unique_id(draft, rid, f"not-who-{by}")
    known = draft.touch({"id": f"{rid}-known", "check": f"exists(target.{fname})",
                         "reason": f"Nobody is recorded as having done {by.replace('_', ' ')} on this, so who may "
                                   f"{action.replace('_', ' ')} it cannot be checked; take {by} on it first."}, quote)
    pre = draft.touch({"id": rid, "check": f"target.{fname} != actor.principal.id",
                       "reason": reason or f"Whoever did {by.replace('_', ' ')} on this, or had their agent do it, "
                                           f"may not {action.replace('_', ' ')}."}, quote)
    without = copy.deepcopy(draft.raw)
    unknown = [fx for fx in _fixtures(draft, obj) if fx.get(fname) is None]
    for fx in unknown:                                    # the examples are data: say who made them, visibly
        fx[fname] = EXAMPLE_OWNER
    if unknown:
        draft.said.append(f"the examples already there are recorded as done by {EXAMPLE_OWNER!r}, so the story "
                          "still runs; anything without a record is refused")
    draft.action(action).setdefault("preconditions", []).extend([known, pre])
    draft.said.append(f"rule {rid}: {pre['reason']}")
    both = [t for t, c in draft.people().items()
            if set(c.get("roles") or []) & set(draft.roles_of(by)) and set(c.get("roles") or []) & set(draft.roles_of(action))]
    if not both and draft.roles_of(by) and draft.roles_of(action):
        both = [draft.add_person(list(dict.fromkeys([draft.roles_of(by)[0], draft.roles_of(action)[0]])),
                                 why=", to show the rule refusing")]
    show_refusal(draft, rid, rid, action, without, both, before=by,
                 says=f"{action.replace('_', ' ')} it, after their own {by.replace('_', ' ')}")
    _demo_tokens(draft, rid, tokens_before)
    return rid


def add_person_only(draft: Draft, action: str, quote: str | None = None) -> str:
    a = draft.action(action)
    rid = f"person-only/{action}"
    if a.get("requires") == "human":
        draft.said.append(f"already a rule: only a person may {action}")
        return rid
    without = copy.deepcopy(draft.raw)
    tokens_before = set(draft.tokens)
    a["requires"] = "human"
    draft.touch(a, quote)
    draft.said.append(f"rule {rid}: only a person may {action} (an agent is refused)")
    roles = set(draft.roles_of(action))
    agents = [t for t, c in draft.agents().items() if set(c.get("roles") or []) & roles
              and set((c.get("on_behalf_of") or {}).get("roles") or []) & roles
              and action in ((c.get("grant") or {}).get("actions") or [])]
    if not agents:
        person = next((c for c in draft.people().values() if set(c.get("roles") or []) & roles), None)
        if person is not None:
            name = draft.free_name()
            r = sorted(set(person.get("roles") or []) & roles)
            draft.tokens[f"t-{name}"] = {"id": name, "kind": "agent", "roles": r,
                                         "on_behalf_of": {"id": person["id"], "roles": list(person.get("roles") or [])},
                                         "grant": {"id": f"g-{name}", "actions": [action]}}
            draft.said.append(f"added an agent {name} acting for {person['id']}, allowed to try {action} "
                              f"(token t-{name}), to show the rule refusing")
            agents = [f"t-{name}"]
    show_refusal(draft, rid, "actor", action, without, agents)
    _demo_tokens(draft, rid, tokens_before)
    return rid


def add_window(draft: Draft, action: str, days: int, fname: str | None = None, since: str | None = None,
               rid: str | None = None, reason: str | None = None, quote: str | None = None) -> str:
    if days <= 0:
        raise SystemExit(fixed(f"--days must be positive, not {days}", "give e.g. --days 30"))
    obj = draft.obj_of(action)
    props = draft.props(obj)
    if fname is None and since is None:
        cands = [k for k, p in props.items() if p.get("type") in ("datetime", "integer")]
        others = [a for a, x in (draft.raw.get("actions") or {}).items()
                  if (x.get("target") or x.get("creates")) == obj and a != action]
        raise SystemExit(fixed("a window counts days from something",
                               f"give --field (one of {', '.join(cands) or 'none'}: a date, or a number of days), "
                               f"or --since ACTION (one of {', '.join(others) or 'none'}) to count from when it was taken"))
    if since is not None:
        draft.action(since)
        fname = fname or f"{since}_at"
        if fname not in props:
            props[fname] = {"type": "datetime", "optional": True}
            draft.touch(draft.raw["objects"][obj])
            draft.action(since).setdefault("effects", []).append({"set": {f"target.{fname}": "now()"}})
            draft.touch(draft.action(since))
            draft.said.append(f"{since} now records when it was taken, in {obj}.{fname} (what was taken before "
                              "has no date, and the window does not hold it back)")
    assert fname is not None
    p = props.get(fname)
    if p is None or p.get("type") not in ("datetime", "integer"):
        raise SystemExit(fixed(f"{obj}.{fname} is not a date or a number of days",
                               "give --field naming one, or --since ACTION"))
    if p["type"] == "integer":
        check, old = f"target.{fname} <= {days}", days + 1
    else:
        check = f"days_since(target.{fname}) <= {days}"
        if p.get("optional"):                             # recorded from now on: what has no date predates it
            check = f"not exists(target.{fname}) or {check}"
        old = (datetime.now(timezone.utc) - timedelta(days=days + 1)).replace(microsecond=0).isoformat()
    what = (since or fname).replace("_", " ")
    rid = _unique_id(draft, rid, f"within-{days}-days")
    pre = draft.touch({"id": rid, "check": check,
                       "reason": reason or f"{action.replace('_', ' ').capitalize()} only within {days} days of {what}."},
                      quote)
    without = copy.deepcopy(draft.raw)
    draft.action(action).setdefault("preconditions", []).append(pre)
    draft.said.append(f"rule {rid}: {pre['reason']}")
    roles = set(draft.roles_of(action))
    who = [t for t, c in draft.people().items() if set(c.get("roles") or []) & roles]
    show_refusal(draft, rid, rid, action, without, who, {fname: old},
                 says=f"{action.replace('_', ' ')} one from {days + 1} days ago")
    return rid


def at_terminal() -> bool:
    """A person typing at a terminal, as far as a local command can tell. Not authentication: it
    keeps an agent that runs commands in a pipeline from making rules a person's by itself."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def person_says_yes(question: str) -> bool:
    return input(f"{question} Type yes to go on: ").strip().lower() == "yes"


def remove_rule(draft: Draft, rid: str) -> None:
    if rid.startswith("person-only/"):
        a = draft.action(rid.split("/", 1)[1])
        if a.get("requires") != "human":
            raise SystemExit(fixed(f"{rid.split('/', 1)[1]} is not person-only", "see `toprope-rule list`"))
        _yours_to_remove(rid, [a])
        a.pop("requires")
        draft.said.append(f"removed {rid}: an agent may take it again, within its grant")
    else:
        for name, a in (draft.raw.get("actions") or {}).items():
            pres = a.get("preconditions") or []
            hit = [p for p in pres if p.get("id") in (rid, f"{rid}-known")]
            if any(p.get("id") == rid for p in hit):
                _yours_to_remove(rid, hit)
                a["preconditions"] = [p for p in pres if not any(p is h for h in hit)]
                if not a["preconditions"]:
                    del a["preconditions"]
                draft.said.append(f"removed {rid} from {name}: {hit[-1].get('reason')}")
                break
        else:
            raise SystemExit(fixed(f"no rule {rid!r}", "see `toprope-rule list` for the ids"))
        settings = draft.story.get("settings") or {}
        for k in [k for k, s in settings.items() if str(s.get("at", "")).endswith(f".preconditions.{rid}")]:
            del settings[k]
            draft.said.append(f"the setting {k} went with it")
            if f"{k}=" in str(draft.story.get("next", "")):
                draft.story["next"] = "Add a rule of your own: `toprope-rule --help`; `toprope-rule list` shows the rules."
    steps = draft.story.get("steps") or []
    keep = [s for s in steps if s.get("rule") != rid and not (s.get("code") == rid)]
    if len(keep) != len(steps):
        draft.story["steps"] = keep
        draft.said.append(f"removed {len(steps) - len(keep)} story step(s) that showed it")
    _remove_demo(draft, rid)


def _yours_to_remove(rid: str, els: list[dict[str, Any]]) -> None:
    """Removing a rule a person made theirs takes a person at the terminal; a proposed one does not."""
    if all(el.get("status") == "proposed" for el in els):
        return
    if not at_terminal():
        raise SystemExit(fixed(f"{rid} is a rule a person made theirs, and removing it needs a person",
                               f"run `toprope-rule remove {rid}` yourself in a terminal; nothing was removed"))
    if not person_says_yes(f"{rid} is a rule a person made theirs; remove it?"):
        raise SystemExit(fixed("not removed", f"type yes to remove {rid}"))


def _remove_demo(draft: Draft, rid: str) -> None:
    """Take back what the rule command added only to show the rule: its example objects, and the
    people and agents it added, unless the story still uses them."""
    demo = (draft.story.get("demos") or {}).pop(rid, None) or {}
    if not draft.story.get("demos"):
        draft.story.pop("demos", None)
    steps = draft.story.get("steps") or []
    used_targets = {s.get("target") for s in steps}
    used_tokens = {s.get("who") for s in steps} | {t for d in (draft.story.get("demos") or {}).values()
                                                   for t in d.get("tokens") or []}
    world = draft.raw.get("world") or {}
    drop = [f for f in demo.get("fixtures") or [] if f not in used_targets]
    if drop:
        world["fixtures"] = [fx for fx in world.get("fixtures") or []
                             if not any(d.get("id") in drop for d in fx.values())]
        draft.said.append(f"removed the example(s) it added: {', '.join(drop)}")
    gone = [t for t in demo.get("tokens") or [] if t in draft.tokens and t not in used_tokens]
    for t in gone:
        del draft.tokens[t]
    if gone:
        draft.said.append(f"removed the token(s) it added to show it: {', '.join(gone)}")


def _proposed_paths(raw: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for kind in ("objects", "links", "actions"):
        for name, el in (raw.get(kind) or {}).items():
            if isinstance(el, dict) and el.get("status") == "proposed":
                out.append((f"{kind}.{name}", el))
            if kind == "actions" and isinstance(el, dict):
                for p in el.get("preconditions") or []:
                    if p.get("status") == "proposed":
                        out.append((f"actions.{name}.preconditions.{p.get('id')}", p))
    for inv in raw.get("invariants") or []:
        if inv.get("status") == "proposed":
            out.append((f"invariants.{inv.get('id')}", inv))
    return out


def confirm(draft: Draft, ids: list[str]) -> None:
    found = _proposed_paths(draft.raw)
    if not found:
        draft.said.append("nothing is proposed: every rule here is already yours")
        return
    picked = [(p, el) for p, el in found if not ids or p in ids or p.rsplit(".", 1)[-1] in ids
              or f"person-only/{p.rsplit('.', 1)[-1]}" in ids]
    missing = [i for i in ids if not any(p == i or p.rsplit(".", 1)[-1] == i or f"person-only/{p.rsplit('.', 1)[-1]}" == i
                                          for p, _ in found)]
    if missing:
        raise SystemExit(fixed(f"not proposed: {', '.join(missing)}",
                               f"confirm one of {', '.join(p for p, _ in found)}, or give no id to confirm all"))
    if not at_terminal():
        raise SystemExit(fixed("confirming makes rules a person's, and needs a person at a terminal",
                               "run `toprope-rule confirm` yourself in a terminal; run by an agent or a script, the "
                               "rules stay proposed (they are enforced either way)"))
    for p, el in picked:
        print(f"  {p}" + (f": {el.get('reason')}" if el.get("reason") else ""))
    if not person_says_yes(f"Make these {len(picked)} yours?"):
        raise SystemExit(fixed("nothing confirmed", "type yes to confirm them"))
    for p, el in picked:
        el["status"] = "confirmed"
        draft.said.append(f"confirmed {p}" + (f": {el.get('reason')}" if el.get("reason") else ""))


def rules_text(draft: Draft) -> str:
    lines = []
    for name, a in (draft.raw.get("actions") or {}).items():
        if a.get("requires") == "human":
            lines.append(f"person-only/{name}  only a person may {name}" + ("  [proposed]" if a.get("status") == "proposed" else ""))
        for p in a.get("preconditions") or []:
            lines.append(f"{p.get('id')}  ({name}) {p.get('reason')}" + ("  [proposed]" if p.get("status") == "proposed" else ""))
    for rid, r in (draft.raw.get("rules") or {}).items():
        lines.append(f"{rid}  (on {r.get('on')}) {r.get('reason')}")
    return "\n".join(lines) + "\n" if lines else "no rules yet\n"


# -- the domain's words --------------------------------------------------------------------------

def add_field(draft: Draft, name: str, kind: str, obj: str | None = None, set_by: list[str] | None = None,
              default: str | None = None, choices: list[str] | None = None) -> None:
    objs = list(draft.raw.get("objects") or {})
    if obj is None:
        if set_by:
            obj = draft.obj_of(set_by[0])
        elif len(objs) == 1:
            obj = objs[0]
        else:
            raise SystemExit(fixed(f"which object gets {name}?", f"give --on, one of {', '.join(objs)}"))
    if obj not in objs:
        raise SystemExit(fixed(f"no object {obj!r}", f"give --on, one of {', '.join(objs)}"))
    if not SNAKE.match(name):
        raise SystemExit(fixed(f"{name!r} is not a field name", "use lowercase letters, digits and `_`"))
    props = draft.props(obj)
    if name in props:
        raise SystemExit(fixed(f"{obj} already has {name}", "choose another name, or rename it with toprope-rename"))
    if choices:
        prop: dict[str, Any] = {"enum": list(choices)}
    elif kind in TYPES:
        prop = {"type": kind}
    else:
        raise SystemExit(fixed(f"no type {kind!r}", f"use one of {', '.join(TYPES)}, or give --choices a,b,c"))
    value = None
    if default is not None:
        if kind == "datetime" and not choices:
            raise SystemExit(fixed("a date field takes no --default", "leave --default out; the field starts empty"))
        _, value = _literal(prop, name, default)
    creators = [a for a, x in (draft.raw.get("actions") or {}).items() if x.get("creates") == obj]
    for a in set_by or []:
        if draft.obj_of(a) != obj:
            raise SystemExit(fixed(f"{a} acts on {draft.obj_of(a)}, not {obj}", "give --set-by an action on that object"))
        if name in (draft.action(a).get("params") or {}):
            raise SystemExit(fixed(f"{a} already takes a param {name}", "choose another field name"))
    fixtures = _fixtures(draft, obj)
    required = (value is not None or not fixtures) and all(c in (set_by or []) for c in creators)
    if not required:
        prop["optional"] = True
    props[name] = prop
    draft.touch(draft.raw["objects"][obj])
    draft.said.append(f"{obj} now has {name} ({'one of ' + ', '.join(choices) if choices else kind}"
                      f"{', optional' if not required else ''})")
    if value is not None:
        for fx in fixtures:
            fx.setdefault(name, value)
        if fixtures:
            draft.said.append(f"the examples of {obj} have {name} = {value}")
    for a in set_by or []:
        act = draft.action(a)
        act.setdefault("params", {})[name] = {k: v for k, v in prop.items() if k != "optional"}
        act.setdefault("effects", []).append({"set": {f"target.{name}": f"params.{name}"}})
        draft.touch(act)
        draft.said.append(f"{a} now takes --{name} and records it")
        sample = value if value is not None else _sample(prop)
        for st in draft.story.get("steps") or []:
            if st.get("action") == a:
                st.setdefault("params", {})[name] = sample
        if any(st.get("action") == a for st in draft.story.get("steps") or []):
            draft.said.append(f"the story's {a} steps give {name} = {sample}")


def add_agent(draft: Draft, name: str, for_: str, may: list[str], roles: list[str] | None) -> None:
    person = next((c for c in draft.people().values() if c.get("id") == for_), None)
    if person is None:
        raise SystemExit(fixed(f"no person {for_!r} in tokens.yaml",
                               f"give --for, one of {', '.join(str(c.get('id')) for c in draft.people().values())}"))
    for a in may:
        draft.action(a)
    _new_token(draft, name)
    beyond = [x for x in roles or [] if x not in (person.get("roles") or [])]
    if beyond:
        raise SystemExit(fixed(f"{for_} does not hold {', '.join(beyond)}, so an agent acting for them may not either",
                               f"give --roles from {', '.join(person.get('roles') or [])}, or give {for_} the role first"))
    r = roles or list(person.get("roles") or [])
    draft.tokens[f"t-{name}"] = {"id": name, "kind": "agent", "roles": r,
                                 "on_behalf_of": {"id": person["id"], "roles": list(person.get("roles") or [])},
                                 "grant": {"id": f"g-{name}", "actions": list(may)}}
    draft.said.append(f"added an agent {name} acting for {for_}, allowed to try {', '.join(may)}; token t-{name}")


def _new_token(draft: Draft, name: str) -> None:
    if not PERSON.match(name):
        raise SystemExit(fixed(f"{name!r} is not a name for a token", "use lowercase letters, digits, `-` and `_`"))
    if f"t-{name}" in draft.tokens or any(isinstance(c, dict) and c.get("id") == name for c in draft.tokens.values()):
        raise SystemExit(fixed(f"{name} is already in tokens.yaml", "choose another name"))


def _roles(draft: Draft, given: str) -> list[str]:
    roles = [r.strip() for r in given.split(",") if r.strip()]
    unknown = [r for r in roles if r not in (draft.raw.get("roles") or [])]
    if unknown:
        raise SystemExit(fixed(f"no role {', '.join(unknown)}", f"add it first: toprope-add role {unknown[0]}"))
    return roles


# -- renaming ------------------------------------------------------------------------------------

def _sub_check(text: Any, pattern: str, new: str) -> Any:
    return re.sub(pattern, new, text) if isinstance(text, str) else text


def rename(draft: Draft, old: str, new: str, kind: str | None = None) -> str:
    raw = draft.raw
    kinds = [k for k, hit in (("object", old in (raw.get("objects") or {})),
                              ("action", old in (raw.get("actions") or {})),
                              ("role", old in (raw.get("roles") or [])),
                              ("field", any(old in (o.get("properties") or {}) for o in (raw.get("objects") or {}).values())))
             if hit and (kind is None or kind == k)]
    if not kinds:
        raise SystemExit(fixed(f"nothing called {old!r}" + (f" is a {kind}" if kind else ""),
                               "give the name of an object, an action, a role or a field, as `toprope-rule list` "
                               "and domain.yaml show it"))
    if len(kinds) > 1:
        raise SystemExit(fixed(f"{old!r} is both a {kinds[0]} and a {kinds[1]}", f"give --kind {kinds[0]} or --kind {kinds[1]}"))
    k = kinds[0]
    rx = {"object": OBJECT, "action": SNAKE, "role": ROLE, "field": SNAKE}[k]
    if not rx.fullmatch(new):
        raise SystemExit(fixed(f"{new!r} is not a name for a {k}",
                               "an object's name starts with a capital letter (Claim); an action's or a field's is "
                               "lowercase letters, digits and `_` (approve_claim); a role's is letters, digits, `_` "
                               "and `-`"))
    {"object": _rename_object, "action": _rename_action, "role": _rename_role, "field": _rename_field}[k](draft, old, new)
    if k in ("object", "action"):
        draft.touch(draft.raw["objects" if k == "object" else "actions"][new])
    elif k == "field":
        for o in draft.raw["objects"].values():
            if new in (o.get("properties") or {}):
                draft.touch(o)
    else:
        for a in draft.raw["actions"].values():
            if new in [r if isinstance(r, str) else r.get("role") for r in a.get("actor") or []]:
                draft.touch(a)
    draft.said.append(f"renamed the {k} {old} to {new}")
    return k


def _renamed_keys(d: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    if new in d:
        raise SystemExit(fixed(f"{new} is already taken", "choose another name"))
    return {(new if k == old else k): v for k, v in d.items()}


def _rename_object(draft: Draft, old: str, new: str) -> None:
    raw = draft.raw
    raw["objects"] = _renamed_keys(raw["objects"], old, new)
    for a in (raw.get("actions") or {}).values():
        for key in ("target", "creates"):
            if a.get(key) == old:
                a[key] = new
    if old in (raw.get("transitions") or {}):
        raw["transitions"] = _renamed_keys(raw["transitions"], old, new)
    for inv in raw.get("invariants") or []:
        if inv.get("on") == old:
            inv["on"] = new
    for link in (raw.get("links") or {}).values():
        for key in ("from", "to"):
            if link.get(key) == old:
                link[key] = new
    for r in (raw.get("rules") or {}).values():
        if str(r.get("on", "")).startswith(f"{old}."):
            r["on"] = f"{new}.{r['on'].split('.', 1)[1]}"
    for fx in (raw.get("world") or {}).get("fixtures") or []:
        if old in fx:
            fx[new] = fx.pop(old)


def _rename_action(draft: Draft, old: str, new: str) -> None:
    raw = draft.raw
    raw["actions"] = _renamed_keys(raw["actions"], old, new)
    for tr in (raw.get("transitions") or {}).values():
        for state, cells in (tr.get("matrix") or {}).items():
            if old in cells:
                tr["matrix"][state] = {(new if k == old else k): v for k, v in cells.items()}
    for a in raw["actions"].values():
        for e in a.get("effects") or []:
            if e.get("reply") == old:
                e["reply"] = new
    for h in (raw.get("handoffs") or {}).values():
        if (h.get("when") or {}).get("action") == old:
            h["when"]["action"] = new
    for c in draft.tokens.values():
        g = (c or {}).get("grant") if isinstance(c, dict) else None
        if g and old in (g.get("actions") or []):
            g["actions"] = [new if x == old else x for x in g["actions"]]
    for st in draft.story.get("steps") or []:
        if st.get("action") == old:
            st["action"] = new
    for s in (draft.story.get("settings") or {}).values():
        s["at"] = re.sub(rf"^actions\.{re.escape(old)}\.", f"actions.{new}.", str(s.get("at", "")))


def _rename_role(draft: Draft, old: str, new: str) -> None:
    raw = draft.raw
    if new in raw["roles"]:
        raise SystemExit(fixed(f"{new} is already a role", "choose another name"))
    raw["roles"] = [new if r == old else r for r in raw["roles"]]
    pat = rf"(['\"]){re.escape(old)}\1"
    for a in (raw.get("actions") or {}).values():
        a["actor"] = [new if r == old else ({**r, "role": new} if isinstance(r, dict) and r.get("role") == old else r)
                      for r in a.get("actor") or []]
        for p in a.get("preconditions") or []:
            p["check"] = _sub_check(p.get("check"), pat, rf"\g<1>{new}\g<1>")
    for inv in raw.get("invariants") or []:
        inv["check"] = _sub_check(inv.get("check"), pat, rf"\g<1>{new}\g<1>")
    for tr in (raw.get("transitions") or {}).values():
        for cells in (tr.get("matrix") or {}).values():
            for c in cells.values():
                if isinstance(c, dict) and old in (c.get("by_role") or {}):
                    c["by_role"] = {(new if k == old else k): v for k, v in c["by_role"].items()}
    for r in (raw.get("rules") or {}).values():
        if isinstance(r.get("requires"), dict):
            r["requires"]["roles"] = [new if x == old else x for x in r["requires"].get("roles") or []]
    actors = (raw.get("world") or {}).get("actors")
    if actors and old in actors:
        raw["world"]["actors"] = {(new if k == old else k): v for k, v in actors.items()}
    for c in draft.tokens.values():
        if isinstance(c, dict):
            for who in (c, c.get("on_behalf_of") or {}):
                if old in (who.get("roles") or []):
                    who["roles"] = [new if x == old else x for x in who["roles"]]
    for s in (draft.story.get("settings") or {}).values():
        if s.get("default") == old:
            s["default"] = new
    for st in draft.story.get("steps") or []:
        if isinstance(st.get("as"), str):
            st["as"] = re.sub(rf"\b{re.escape(old)}\b", new, st["as"])


def _rename_field(draft: Draft, old: str, new: str) -> None:
    raw = draft.raw
    owners = [o for o, x in raw["objects"].items() if old in (x.get("properties") or {})]
    for o in owners:
        raw["objects"][o]["properties"] = _renamed_keys(raw["objects"][o]["properties"], old, new)
    pat = rf"\b(target|new)\.{re.escape(old)}\b"
    for a in (raw.get("actions") or {}).values():
        if (a.get("target") or a.get("creates")) not in owners:
            continue
        for p in a.get("preconditions") or []:
            p["check"] = _sub_check(p.get("check"), pat, rf"\g<1>.{new}")
        for e in a.get("effects") or []:
            if e.get("set"):
                e["set"] = {(f"target.{new}" if k == f"target.{old}" else k): _sub_check(v, pat, rf"\g<1>.{new}")
                            for k, v in e["set"].items()}
    for name, a in (raw.get("actions") or {}).items():          # a param that records the field follows it
        sets = [e for e in a.get("effects") or [] if (e.get("set") or {}).get(f"target.{new}") == f"params.{old}"]
        if sets and old in (a.get("params") or {}) and (a.get("target") or a.get("creates")) in owners:
            a["params"] = _renamed_keys(a["params"], old, new)
            for e in sets:
                e["set"][f"target.{new}"] = f"params.{new}"
            for p in a.get("preconditions") or []:
                p["check"] = _sub_check(p.get("check"), rf"\bparams\.{re.escape(old)}\b", f"params.{new}")
            for st_ in (draft.story.get("settings") or {}).values():
                if str(st_.get("at", "")).startswith(f"actions.{name}."):
                    st_["check"] = _sub_check(st_.get("check"), rf"\bparams\.{re.escape(old)}\b", f"params.{new}")
            for st in draft.story.get("steps") or []:
                if st.get("action") == name and old in (st.get("params") or {}):
                    st["params"] = {(new if k == old else k): v for k, v in st["params"].items()}
    for inv in raw.get("invariants") or []:
        if inv.get("on") in owners:
            inv["check"] = _sub_check(inv.get("check"), pat, rf"\g<1>.{new}")
    for o in owners:
        tr = (raw.get("transitions") or {}).get(o)
        if tr and tr.get("field") == old:
            tr["field"] = new
        for r in (raw.get("rules") or {}).values():
            if r.get("on") == f"{o}.{old}":
                r["on"] = f"{o}.{new}"
    for fx in (raw.get("world") or {}).get("fixtures") or []:
        for o, data in fx.items():
            if o in owners and old in data:
                fx[o] = {(new if k == old else k): v for k, v in data.items()}
    for s in (draft.story.get("settings") or {}).values():
        s["check"] = _sub_check(s.get("check"), pat, rf"\g<1>.{new}")


# -- the commands --------------------------------------------------------------------------------

def _ask_person(draft: Draft) -> str:
    """At a terminal, the person who typed the command may make the change theirs; anywhere else
    (an agent, a script) it stays proposed, with the command that confirms it."""
    if not at_terminal():
        draft.said.append(f"written as proposed: no person confirmed it at a terminal (a person makes it theirs "
                          f"with `{hint('toprope-rule confirm')}`); it is enforced either way")
        return "proposed"
    for line in draft.said[draft.printed:]:
        print(line)
    draft.printed = len(draft.said)
    if person_says_yes("Make this change yours (confirmed)? Anything else writes it as proposed."):
        return "confirmed"
    draft.said.append("written as proposed")
    return "proposed"


def _done(draft: Draft, check_harness: bool = True) -> None:
    draft.save(check_harness=check_harness, confirm=_ask_person)
    for line in draft.said[draft.printed:]:
        print(line)
    from .start import report_story
    report_story(draft.where)
    print(f"see it: {hint('toprope-try')}")


def rule_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-rule", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="the domain's directory (default: here)")
    sub = ap.add_subparsers(dest="kind", metavar="KIND")
    sub.add_parser("list", help="the domain's rules, with the id each is removed or confirmed by")
    t = sub.add_parser("threshold", help="above (or below) a value, an action needs a role")
    t.add_argument("--action", required=True, help="the action the rule holds back, e.g. approve_request")
    t.add_argument("--when", required=True, metavar="'FIELD OP VALUE'", help='when the rule applies, e.g. "amount > 1000"')
    t.add_argument("--needs", required=True, metavar="ROLE", help="the role that may still take the action then")
    s = sub.add_parser("no-self-approval", help="whoever made it theirs (submitted, created) may not take the action")
    s.add_argument("--action", required=True, help="the action, e.g. approve_request")
    s.add_argument("--by", help="the action that makes it someone's (found if one records who took it)")
    p = sub.add_parser("person-only", help="only a person may take the action; an agent is refused")
    p.add_argument("--action", required=True)
    w = sub.add_parser("window", help="the action is allowed only within a number of days")
    w.add_argument("--action", required=True)
    w.add_argument("--days", required=True, type=int)
    w.add_argument("--field", help="a date field, or a field that counts days, to measure from")
    w.add_argument("--since", metavar="ACTION", help="count from when this action was taken (recorded from now on)")
    for x in (t, s, w):
        x.add_argument("--id", help="the rule's id (refusals carry it as their code)")
        x.add_argument("--reason", help="the reason a refusal gives (default: written from the rule)")
    r = sub.add_parser("remove", help="remove a rule by its id (see list)")
    r.add_argument("id")
    c = sub.add_parser("confirm", help="make drafted (`proposed`) rules yours; with no id, all of them")
    c.add_argument("ids", nargs="*")
    return ap


def add_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-add", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="the domain's directory (default: here)")
    sub = ap.add_subparsers(dest="what", metavar="WHAT")
    r = sub.add_parser("role", help="a role")
    r.add_argument("name")
    r.add_argument("--may", default="", metavar="ACTION,...", help="actions the role may take")
    p = sub.add_parser("person", help="a person, with a token in tokens.yaml to act as them")
    p.add_argument("name")
    p.add_argument("--roles", required=True, metavar="ROLE,...")
    a = sub.add_parser("agent", help="an agent acting for a person, with a token and a grant")
    a.add_argument("name")
    a.add_argument("--for", dest="for_", required=True, metavar="PERSON")
    a.add_argument("--may", required=True, metavar="ACTION,...", help="the actions its grant allows")
    a.add_argument("--roles", metavar="ROLE,...", help="its roles (default: the person's)")
    f = sub.add_parser("field", help="a field of an object, optionally given when an action is taken")
    f.add_argument("name")
    f.add_argument("--type", default="integer", help=f"one of {', '.join(TYPES)} (default: integer)")
    f.add_argument("--choices", metavar="A,B,...", help="instead of --type: one of these words")
    f.add_argument("--on", metavar="OBJECT", help="the object (default: the action's, or the only one)")
    f.add_argument("--set-by", metavar="ACTION,...", help="actions that take it as a param and record it")
    f.add_argument("--default", help="its value in the examples already there")
    return ap


def rename_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-rename", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old", help="an object, action, role or field as domain.yaml names it")
    ap.add_argument("new", help="its new name")
    ap.add_argument("--kind", choices=["object", "action", "role", "field"], help="when the name is used twice")
    ap.add_argument("--dir", default=".", help="the domain's directory (default: here)")
    return ap


def _reads(text: Any, pattern: str) -> bool:
    return isinstance(text, str) and re.search(pattern, text) is not None


def remove_field(draft: Draft, name: str, obj: str | None = None) -> None:
    owners = [o for o, x in draft.raw["objects"].items() if name in (x.get("properties") or {}) and obj in (None, o)]
    if not owners:
        raise SystemExit(fixed(f"no field {name!r}", "give a field as domain.yaml names it (`toprope-rule list` shows "
                               "the rules that read fields)"))
    if len(owners) > 1:
        raise SystemExit(fixed(f"{name} is a field of {', '.join(owners)}", f"give --on, one of {', '.join(owners)}"))
    o = owners[0]
    pat = rf"\b(target|new)\.{re.escape(name)}\b"
    where = []
    for an, a in (draft.raw.get("actions") or {}).items():
        if (a.get("target") or a.get("creates")) != o:
            continue
        where += [f"rule {p.get('id')}" for p in a.get("preconditions") or [] if _reads(p.get("check"), pat)]
        where += [f"an effect of {an}" for e in a.get("effects") or [] for v in (e.get("set") or {}).values()
                  if _reads(v, pat)]
    where += [f"invariant {i.get('id')}" for i in draft.raw.get("invariants") or [] if i.get("on") == o
              and _reads(i.get("check"), pat)]
    if (draft.raw.get("transitions") or {}).get(o, {}).get("field") == name:
        where.append(f"the states of {o}")
    where += [f"outcome rule {r}" for r, x in (draft.raw.get("rules") or {}).items() if x.get("on") == f"{o}.{name}"]
    if where:
        raise SystemExit(fixed(f"{o}.{name} is still used: {', '.join(where)}",
                               "remove those first (`toprope-rule remove ID` for a rule); nothing was removed"))
    del draft.raw["objects"][o]["properties"][name]
    draft.touch(draft.raw["objects"][o])
    for fx in (draft.raw.get("world") or {}).get("fixtures") or []:
        if o in fx:
            fx[o].pop(name, None)
    for an, a in (draft.raw.get("actions") or {}).items():
        if (a.get("target") or a.get("creates")) != o:
            continue
        feeds = []
        for e in list(a.get("effects") or []):
            st = e.get("set") or {}
            if f"target.{name}" in st:
                v = str(st.pop(f"target.{name}"))
                feeds += re.findall(r"\bparams\.(\w+)", v)
                if not st:
                    a["effects"].remove(e)
                draft.touch(a)
        if not a.get("effects"):
            a.pop("effects", None)
        text = " ".join(str(p.get("check")) for p in a.get("preconditions") or []) + " ".join(
            str(v) for e in a.get("effects") or [] for v in (e.get("set") or {}).values())
        for prm in feeds:                                # a param that only recorded the field goes too
            if prm in (a.get("params") or {}) and not re.search(rf"\bparams\.{prm}\b", text):
                del a["params"][prm]
                if not a["params"]:
                    del a["params"]
                for st in draft.story.get("steps") or []:
                    if st.get("action") == an and prm in (st.get("params") or {}):
                        st["params"].pop(prm)
                        if not st["params"]:
                            st.pop("params")
                draft.said.append(f"{an} no longer takes --{prm}")
    draft.said.append(f"removed the field {o}.{name}")


def remove_role(draft: Draft, role: str) -> None:
    raw = draft.raw
    if role not in (raw.get("roles") or []):
        raise SystemExit(fixed(f"no role {role!r}", f"give one of {', '.join(raw.get('roles') or [])}"))
    pat = rf"(['\"]){re.escape(role)}\1"
    where = []
    for an, a in (raw.get("actions") or {}).items():
        roles = [r if isinstance(r, str) else r.get("role") for r in a.get("actor") or []]
        if roles == [role]:
            where.append(f"{an}, which only {role} may take")
        where += [f"rule {p.get('id')}" for p in a.get("preconditions") or [] if _reads(p.get("check"), pat)]
    for tr in (raw.get("transitions") or {}).values():
        for st, cells in (tr.get("matrix") or {}).items():
            where += [f"the cell {st}/{c}" for c, v in cells.items() if isinstance(v, dict) and role in (v.get("by_role") or {})]
    where += [f"outcome rule {r}" for r, x in (raw.get("rules") or {}).items()
              if isinstance(x.get("requires"), dict) and role in x["requires"].get("roles") or []]
    where += [f"the token {t}" for t, c in draft.tokens.items() if isinstance(c, dict) and (
        role in (c.get("roles") or []) or role in ((c.get("on_behalf_of") or {}).get("roles") or []))]
    if where:
        raise SystemExit(fixed(f"the role {role} is still used: {', '.join(where)}",
                               "remove those first (`toprope-rule remove ID`, `toprope-remove person NAME`); "
                               "nothing was removed"))
    raw["roles"] = [r for r in raw["roles"] if r != role]
    for a in (raw.get("actions") or {}).values():
        kept = [r for r in a.get("actor") or [] if (r if isinstance(r, str) else r.get("role")) != role]
        if len(kept) != len(a.get("actor") or []):
            a["actor"] = kept
            draft.touch(a)
    draft.said.append(f"removed the role {role}")


def remove_person(draft: Draft, name: str) -> None:
    tokens = [t for t, c in draft.tokens.items() if isinstance(c, dict) and c.get("id") == name]
    if not tokens:
        raise SystemExit(fixed(f"no person or agent {name!r} in tokens.yaml", "give one of " + ", ".join(
            str(c.get("id")) for c in draft.tokens.values() if isinstance(c, dict))))
    agents = [t for t, c in draft.tokens.items() if isinstance(c, dict) and (c.get("on_behalf_of") or {}).get("id") == name]
    if agents:
        raise SystemExit(fixed(f"{name} has agents acting for them: {', '.join(agents)}",
                               "remove those first (`toprope-remove person <the agent's name>`); nothing was removed"))
    steps = draft.story.get("steps") or []
    keep = [st for st in steps if st.get("who") not in tokens]
    for t in tokens:
        del draft.tokens[t]
    draft.said.append(f"removed {name} (token {', '.join(tokens)})")
    if len(keep) != len(steps):
        draft.story["steps"] = keep
        draft.said.append(f"removed {len(steps) - len(keep)} story step(s) in which {name} acted")


def remove_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-remove", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="the domain's directory (default: here)")
    sub = ap.add_subparsers(dest="what", metavar="WHAT")
    f = sub.add_parser("field", help="a field no rule, effect or state reads (its values leave the examples)")
    f.add_argument("name")
    f.add_argument("--on", metavar="OBJECT", help="the object, when several have the field")
    r = sub.add_parser("role", help="a role no rule, cell or person holds (it leaves the actions' actor lists)")
    r.add_argument("name")
    p = sub.add_parser("person", help="a person or an agent from tokens.yaml, with the story steps they act in")
    p.add_argument("name")
    return ap


def remove_main(argv: list[str] | None = None) -> None:
    a = remove_parser().parse_args(argv)
    draft = Draft.open(Path(a.dir))
    draft.quote = _typed("toprope-remove", argv)
    if a.what is None:
        remove_parser().print_help()
        return
    if a.what == "field":
        remove_field(draft, a.name, a.on)
    elif a.what == "role":
        remove_role(draft, a.name)
    else:
        remove_person(draft, a.name)
    _done(draft)


def _typed(prog: str, argv: list[str] | None) -> str:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--dir" in args:                                   # where it ran is not what it said
        i = args.index("--dir")
        del args[i:i + 2]
    return shlex.join([prog, *args])


def _list(given: str | None) -> list[str]:
    return [x.strip() for x in (given or "").split(",") if x.strip()]


def rule_main(argv: list[str] | None = None) -> None:
    a = rule_parser().parse_args(argv)
    draft = Draft.open(Path(a.dir))
    draft.quote = _typed("toprope-rule", argv)
    if a.kind in (None, "list"):
        print(rules_text(draft), end="")
        if a.kind is None:
            print("add one: toprope-rule threshold | no-self-approval | person-only | window --help")
        return
    if a.kind == "threshold":
        add_threshold(draft, a.action, a.when, a.needs, a.id, a.reason)
    elif a.kind == "no-self-approval":
        add_no_self_approval(draft, a.action, a.by, a.id, a.reason)
    elif a.kind == "person-only":
        add_person_only(draft, a.action)
    elif a.kind == "window":
        add_window(draft, a.action, a.days, a.field, a.since, a.id, a.reason)
    elif a.kind == "remove":
        remove_rule(draft, a.id)
    elif a.kind == "confirm":
        confirm(draft, a.ids)
    _done(draft, check_harness=a.kind not in ("confirm", "remove"))


def add_main(argv: list[str] | None = None) -> None:
    a = add_parser().parse_args(argv)
    draft = Draft.open(Path(a.dir))
    draft.quote = _typed("toprope-add", argv)
    if a.what is None:
        add_parser().print_help()
        return
    if a.what == "role":
        draft.add_role(a.name)
        if not draft.said:
            draft.said.append(f"{a.name} is already a role")
        for act in _list(a.may):
            draft.let_take(a.name, act)
    elif a.what == "person":
        _new_token(draft, a.name)
        draft.add_person(_roles(draft, a.roles), a.name)
    elif a.what == "agent":
        add_agent(draft, a.name, a.for_, _list(a.may), _roles(draft, a.roles) if a.roles else None)
    elif a.what == "field":
        add_field(draft, a.name, a.type, a.on, _list(a.set_by), a.default, _list(a.choices) or None)
    _done(draft)


def rename_main(argv: list[str] | None = None) -> None:
    a = rename_parser().parse_args(argv)
    draft = Draft.open(Path(a.dir))
    draft.quote = _typed("toprope-rename", argv)
    rename(draft, a.old, a.new, a.kind)
    _done(draft)


__all__ = ["Draft", "remove_main", "remove_parser", "add_field", "add_main", "add_no_self_approval", "add_parser", "add_person_only", "add_threshold",
           "add_window", "confirm", "remove_rule", "rename", "rename_main", "rename_parser", "rule_main", "rule_parser"]
