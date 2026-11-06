"""The mechanical layer (ADR-0035): what the declaration says, tested without examples."""
import copy

from test_decl import schema_doc_domain

from toprope.check import change_check
from toprope.decl import Domain
from toprope.harness import run_harness
from toprope.harness.mechanical import unreachable_from_creation


def no_examples():
    raw = schema_doc_domain()
    raw["world"]["fixtures"] = []
    raw["scenarios"] = []
    return raw


def test_cells_run_without_any_example():
    r = run_harness(Domain.model_validate(no_examples()), levels=("model",), explore_examples=0, races=False)
    m = r.coverage["mechanical"]
    assert r.coverage["cells"]["covered"]["model"] == 0                     # the example layer has nothing
    assert m["cells"] > 0 and m["samples"] >= m["cells"] and not m["no_sample"]


def test_a_non_inductive_invariant_is_a_warning_naming_the_cell_and_start():
    r = run_harness(Domain.model_validate(no_examples()), levels=("model",), explore_examples=0, races=False)
    assert r.ok
    (w, *_) = [w for w in r.warnings if w.case.startswith("mechanical:Experiment.approved.launch_experiment.")]
    assert w.kind == "inductive" and w.detail["start"]["status"] == "approved" and "approved_by" not in w.detail["start"]
    strong = no_examples()                                                  # rule the start out: no warning
    strong["invariants"].append({"id": "approved-has-approver", "on": "Experiment",
                                 "check": "target.status != 'approved' or exists(target.approved_by)",
                                 "reason": "An approved experiment names its approver."})
    r2 = run_harness(Domain.model_validate(strong), levels=("model",), explore_examples=0, races=False)
    assert not [w for w in r2.warnings if ".launch_experiment." in w.case]


def test_a_broken_surface_is_caught_without_examples():
    from test_harness import _renamed

    import toprope.adapters.mcp as gen

    def broken_build(ex, credentials, **kw):
        real = gen._action_tool
        try:
            first = next(iter(ex.d.actions))
            gen._action_tool = lambda ex_, c, name, a: _renamed(real(ex_, c, first, ex_.d.actions[first]), name)
            return gen.build_server(ex, credentials, **kw)
        finally:
            gen._action_tool = real
    r = run_harness(Domain.model_validate(no_examples()), levels=("model", "mcp"), build_server=broken_build,
                    explore_examples=0, races=False)
    assert any(f.kind == "parity" and f.case.startswith("mechanical:") for f in r.findings)


def test_stages_unreachable_from_creation():
    raw = schema_doc_domain()
    raw["actions"]["open_experiment"] = {"description": "Open.", "actor": ["pm"], "creates": "Experiment",
                                         "params": {"name": {"type": "string"}}}
    assert unreachable_from_creation(Domain.model_validate(raw)) == {"Experiment": ["ended", "decided"]}
    r = change_check(Domain.model_validate(raw), None, examples=5)
    assert ("warning", "state:Experiment.ended") in [(p.severity, p.where) for p in r.checks["semantic"].problems]


def test_the_change_check_reports_non_inductive_invariants_as_warnings(tmp_path):
    from toprope.incremental import ResultCache, run_tests
    d = Domain.model_validate(no_examples())
    r = change_check(d, None, examples=5)
    assert r.checks["harness"].ok
    assert any(p.severity == "warning" and p.where.startswith("inductive:mechanical:") for p in r.checks["harness"].problems)
    cache = ResultCache(tmp_path / "c")
    run_tests(d, examples=5, cache=cache)
    again = run_tests(d, examples=5, cache=cache)                          # cached, warnings kept
    assert again.stats["run"] == 0 and again.warnings
    text = copy.deepcopy(no_examples())
    text["glossary"]["readout"] = "A first look."
    assert run_tests(Domain.model_validate(text), examples=5, cache=cache).stats["run"] == 0
