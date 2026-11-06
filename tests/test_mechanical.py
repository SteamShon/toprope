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


# -- review findings -----------------------------------------------------------------------------
def _mech(raw, actions=None):
    from toprope.harness.mechanical import run_mechanical
    from toprope.harness.run import NOW
    from toprope.harness.surfaces import ModelSurface
    d = Domain.model_validate(raw)
    return run_mechanical(d, {"model": ModelSurface(d, lambda: NOW)}, lambda: NOW, samples=3, actions=actions)


def test_a_cell_s_objects_do_not_depend_on_which_cells_ran():
    raw = no_examples()
    whole = {(f.case, str(f.detail.get("start"))) for f in _mech(raw).findings if ".launch_experiment." in f.case}
    alone = {(f.case, str(f.detail.get("start"))) for f in _mech(raw, {"launch_experiment"}).findings}
    assert whole and whole == alone


def test_selection_misses_ignore_warnings(tmp_path):
    from toprope.incremental import ResultCache, run_tests, selection_misses, tests_of
    d = Domain.model_validate(no_examples())
    cache = ResultCache(tmp_path / "c")
    run_tests(d, examples=0, cache=cache)
    t = next(t for t in tests_of(d, examples=0) if t.id == "mechanical:launch_experiment")
    assert cache.get(t.key)                                                 # it holds a warning
    cache.put(t.key, t.id, [])                                              # a cached run that missed it
    assert selection_misses(d, examples=0, cache=cache) == []


def test_ref_params_name_a_generated_object():
    """A `ref` param must name an object that exists, or the cell tests a dangling reference."""
    raw = no_examples()
    raw["actions"]["switch_metric"] = {"description": "Switch the primary metric.", "actor": ["pm"],
                                       "target": "Experiment", "params": {"metric": {"ref": "Metric"}},
                                       "effects": [{"set": {"target.primary_metric": "params.metric"}}]}
    for state, row in raw["transitions"]["Experiment"]["matrix"].items():
        row["switch_metric"] = state if state == "draft" else "n/a"
    raw["invariants"].append({"id": "metric-exists", "on": "Experiment", "check": "exists(target.primary_metric.name)",
                              "reason": "The primary metric is a real metric."})
    r = run_harness(Domain.model_validate(raw), levels=("model",), explore_examples=0, races=False)
    assert not [w for w in r.warnings if ".switch_metric." in w.case]


def test_a_cell_no_object_can_test_is_a_warning():
    raw = no_examples()
    raw["invariants"].append({"id": "approved-never", "on": "Experiment",
                              "check": "target.status != 'approved' or target.name == 'never generated'",
                              "reason": "Unsatisfiable by the generator."})
    r = run_harness(Domain.model_validate(raw), levels=("model",), explore_examples=0, races=False)
    assert r.ok and any(w.kind == "no-sample" and ".approved." in w.case for w in r.warnings)


def test_linked_objects_fill_their_required_links():
    import random

    from toprope.harness.mechanical import Generator
    raw = no_examples()
    raw["links"]["metric_owner"] = {"from": "Hypothesis", "to": "Metric", "cardinality": "many-to-one", "required": True}
    _, extras = Generator(Domain.model_validate(raw), random.Random(0)).make("Experiment", "draft")
    hyp = next(x for o, x in extras if o == "Hypothesis")
    assert "metric_owner" in hyp
