"""The natural-language check with an LLM reading the change as structure (ADR-0009)."""

from __future__ import annotations

import copy
import json
import sys

from test_decl import schema_doc_domain

from toprope.check import change_check
from toprope.check.nl_llm import CommandChecker, build_prompt, parse
from toprope.decl.models import Domain


def bypass(raw):
    raw = copy.deepcopy(raw)
    raw["actions"]["approve_quickly"] = {"description": "Approve a small experiment.", "actor": ["eng"],
                                         "target": "Experiment"}
    m = raw["transitions"]["Experiment"]["matrix"]
    m["draft"]["approve_quickly"] = "approved"
    for s in ("approved", "running", "ended", "decided"):
        m[s]["approve_quickly"] = "n/a"
    return raw


def fake(tmp_path, answer: dict | str, code: int = 0) -> list[str]:
    script = tmp_path / "llm.py"
    script.write_text("import sys, json\nprompt = sys.stdin.read()\nopen(sys.argv[1], 'w').write(prompt)\n"
                      f"print({json.dumps(answer) if isinstance(answer, str) else repr(json.dumps(answer))})\n"
                      f"sys.exit({code})\n")
    return [sys.executable, str(script), str(tmp_path / "prompt.txt")]


def test_the_checker_sees_the_change_the_capability_diff_and_answers_warnings(tmp_path):
    old = schema_doc_domain()
    old["actions"]["approve_experiment"]["requires"] = "human"
    new = bypass(old)
    cmd = fake(tmp_path, {"conflicts": [{"where": "actions.approve_quickly",
                                         "problem": "goes around the person-only approval"}]})
    r = change_check(Domain.model_validate(new), Domain.model_validate(old), nl=CommandChecker(cmd))
    assert [(p.severity, p.where) for p in r.checks["nl"].problems] == [("warning", "actions.approve_quickly")]
    prompt = (tmp_path / "prompt.txt").read_text()
    assert "## action:approve_quickly" in prompt and "can now be reached by a new path" in prompt


def test_a_failed_checker_is_reported_not_passed(tmp_path):
    old = schema_doc_domain()
    r = change_check(Domain.model_validate(bypass(old)), Domain.model_validate(old),
                     nl=CommandChecker(fake(tmp_path, "no json here")))
    assert not r.checks["nl"].ran and "did not answer with the JSON" in r.checks["nl"].note
    r = change_check(Domain.model_validate(bypass(old)), Domain.model_validate(old),
                     nl=CommandChecker(fake(tmp_path, {"conflicts": []}, code=3)))
    assert not r.checks["nl"].ran and "exited 3" in r.checks["nl"].note


def test_parse_and_prompt_without_a_base():
    assert parse('ok {"conflicts": [{"where": "rules.x", "problem": "p"}]}') == [("rules.x", "p")]
    assert "--- Outcome rules ---" in build_prompt(None, Domain.model_validate(schema_doc_domain()), [])
