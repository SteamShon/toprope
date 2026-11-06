import copy
from datetime import datetime, timedelta, timezone

import pytest

from test_decl import schema_doc_domain
from toprope.decl import Domain
from toprope.semantics import Actor, Command, Grant, ReferenceModel, project
from toprope.store import ConcurrencyError, MemoryEventStore

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
clock = lambda: NOW  # noqa: E731

ANA = Actor("ana", "person", ("approver",))
ELI = Actor("eli", "person", ("eng",))
PAT = Actor("pat", "person", ("pm",))
BOT = Actor("bot", "agent", ("approver",))


def domain(mutate=None) -> Domain:
    raw = schema_doc_domain()
    if mutate:
        mutate(raw)
    return Domain.model_validate(raw)


def model(mutate=None, **kw) -> ReferenceModel:
    return ReferenceModel(domain(mutate), clock=clock, **kw)


def do(m, actor, action, target, **kw):
    return m.execute(Command(actor, action, target, kw.pop("params", {}), **kw))


# -- the schema doc's own scenarios, run through the oracle ----------------------------------
MATRIX_CODES = {"matrix", "not-applicable", "undecided"}


def run_scenario(sc, d: Domain):
    m = ReferenceModel(d, clock=clock)
    if "from_world" not in sc.given:
        for obj, data in sc.given.items():
            m.seed(obj, data)
    for step in sc.steps:
        actor = Actor(f"{step.actor['role']}-1", "person", (step.actor["role"],))
        exp = step.expect
        if step.read:
            target = step.read["target"]
            if "actions_shown" in exp:
                assert sorted(m.allowed_actions(target, actor)) == sorted(exp["actions_shown"]), step
            for f in exp.get("fields_include", []):
                assert f in m.state(target), (step, f)
            continue
        out = do(m, actor, step.do, step.target, params=step.params)
        if "denied_by" in exp:
            want = exp["denied_by"]
            assert out.status == "denied", (step, out)
            assert (out.code in MATRIX_CODES) if want == "matrix" else out.code == want, (step, out)
            if exp.get("reason_shown"):
                assert out.reason
        if "state" in exp:
            assert out.ok, (step, out)
            for path, val in exp["state"].items():
                oid, field = path.split(".", 1)
                assert m.state(oid)[field] == val
        if exp.get("decision_recorded"):
            assert any(e.kind == "decision" for e in out.events)


def test_schema_doc_scenarios_pass_on_the_oracle():
    d = domain()
    assert len(d.scenarios) == 3
    for sc in d.scenarios:
        run_scenario(sc, d)


# -- steps 4-10 ------------------------------------------------------------------------------
def test_happy_path_and_events():
    m = model()
    out = do(m, ANA, "approve_experiment", "E-onboarding", params={"note": "ok"})
    assert out.ok and out.state["status"] == "approved" and out.state["approved_by"] == "ana"
    assert [e.type for e in out.events] == ["ExperimentApproveExperiment", "DecisionRecorded"]
    assert [e.version for e in out.events] == [2, 3]
    out = do(m, ELI, "launch_experiment", "E-onboarding")
    assert out.ok and out.state["status"] == "running" and out.state["started_at"] == NOW.isoformat()


def test_denials_carry_codes_and_land_in_the_attempts_stream():
    m = model()
    assert do(m, ELI, "approve_experiment", "E-onboarding").code == "actor"
    assert do(m, ELI, "launch_experiment", "E-onboarding").code == "matrix"
    assert do(m, ANA, "approve_experiment", "E-bare").code == "has-guardrails"
    attempts = m.store.read_attempts("E-onboarding")
    assert [a.payload["code"] for a in attempts] == ["actor", "matrix"]
    assert m.store.version("E-onboarding") == 1, "attempts never bump the stream version"


def test_not_applicable_and_undecided_cells():
    m = model()
    m.seed("Experiment", {"id": "E-run", "status": "running", "approved_by": "ana", "started_at": "x"})
    m.seed("Experiment", {"id": "E-end", "status": "ended", "approved_by": "ana", "started_at": "x"})
    assert do(m, ELI, "launch_experiment", "E-run").code == "not-applicable"
    assert do(m, ELI, "launch_experiment", "E-end").code == "undecided"


def test_missing_cell_is_undecided():
    def drop(raw):
        del raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"]
    assert do(model(drop), ELI, "launch_experiment", "E-onboarding").code == "undecided"


def test_by_role_cells():
    def by_role(raw):
        raw["roles"].append("lead")
        raw["actions"]["approve_experiment"]["actor"] = ["approver", "lead"]
        raw["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = {
            "by_role": {"lead": {"deny": "Leads do not approve their own team's experiments."}, "approver": "approved"}}
    m = model(by_role)
    assert do(m, Actor("lee", "person", ("lead",)), "approve_experiment", "E-onboarding").code == "matrix"
    assert do(m, ANA, "approve_experiment", "E-onboarding").ok


def test_relation_based_actor_rule():
    def owner_rule(raw):
        raw["objects"]["Experiment"]["properties"]["owner"] = {"type": "string", "optional": True}
        raw["actions"]["approve_experiment"]["actor"] = [{"role": "approver", "where": "actor.id != target.owner"}]
        raw["world"]["fixtures"][3]["Experiment"]["owner"] = "ana"
    m = model(owner_rule)
    assert do(m, ANA, "approve_experiment", "E-onboarding").code == "actor"
    assert do(m, Actor("abe", "person", ("approver",)), "approve_experiment", "E-onboarding").ok


def test_agents_need_principal_grant_and_both_rules():
    m = model()
    g = Grant("g1", frozenset({"approve_experiment"}), expires_at=NOW + timedelta(hours=1))
    assert do(m, BOT, "approve_experiment", "E-onboarding").code == "actor"                          # no grant
    assert do(m, BOT, "approve_experiment", "E-onboarding", on_behalf_of=PAT, grant=g).code == "actor"  # pm can't
    expired = Grant("g0", frozenset({"approve_experiment"}), expires_at=NOW)
    assert do(m, BOT, "approve_experiment", "E-onboarding", on_behalf_of=ANA, grant=expired).code == "actor"
    out = do(m, BOT, "approve_experiment", "E-onboarding", on_behalf_of=ANA, grant=g, thread_id="t1")
    assert out.ok and out.events[0].on_behalf_of == {"id": "ana", "kind": "person"} and out.events[0].grant == "g1"
    assert out.events[0].thread_id == "t1"


def test_requires_human():
    def human(raw):
        raw["actions"]["approve_experiment"]["requires"] = "human"
    g = Grant("g1", frozenset({"approve_experiment"}))
    out = do(model(human), BOT, "approve_experiment", "E-onboarding", on_behalf_of=ANA, grant=g)
    assert out.code == "actor" and "person" in out.reason


def test_invariant_guard_rejects_inconsistent_declaration():
    def skip_approval(raw):  # matrix allows launching a draft: contradicts running-has-approver
        raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"
    m = model(skip_approval)
    out = do(m, ELI, "launch_experiment", "E-onboarding")
    assert out.status == "rejected" and out.code == "invariant-guard"
    assert [a.type for a in m.store.read_attempts("E-onboarding")] == ["InvariantGuardTriggered"]
    assert m.state("E-onboarding")["status"] == "draft"


def test_create_action():
    def creatable(raw):
        raw["actions"]["design_experiment"] = {
            "description": "Draft an experiment.", "actor": ["pm"], "creates": "Experiment",
            "params": {"name": {"type": "string"}, "planned_days": {"type": "integer"}}}
    m = model(creatable)
    out = do(m, PAT, "design_experiment", "E-new", params={"name": "New", "planned_days": 7})
    assert out.ok and m.state("E-new") == {"id": "E-new", "name": "New", "planned_days": 7, "status": "draft"}
    assert do(m, PAT, "design_experiment", "E-new", params={"name": "Again", "planned_days": 7}).code == "exists"
    assert do(m, PAT, "design_experiment", "E-x", params={"name": "X"}).code == "invalid-command"
    assert do(m, PAT, "design_experiment", "E-y", params={"name": "Y", "planned_days": 7, "approved_by": "m"}).code == "invalid-command"
    assert do(m, ELI, "design_experiment", "E-new", params={"name": "N", "planned_days": 7}).code == "actor", \
        "existence is not revealed to actors whose role cannot act"


def test_unknown_actor_and_action():
    m = model()
    assert m.execute(Command(None, "approve_experiment", "E-onboarding")).code == "unauthenticated"
    assert do(m, ANA, "nope", "E-onboarding").code == "unknown-action"
    assert do(m, ANA, "approve_experiment", "E-ghost").code == "not-found"


# -- steps 2, 3, 11 --------------------------------------------------------------------------
def test_idempotency_is_scoped_by_actor_action_target():
    m = model()
    first = do(m, ANA, "approve_experiment", "E-onboarding", idempotency_key="k1")
    again = do(m, ANA, "approve_experiment", "E-onboarding", idempotency_key="k1")
    assert first.ok and again == first and m.store.version("E-onboarding") == 3
    other = do(m, Actor("abe", "person", ("approver",)), "approve_experiment", "E-onboarding", idempotency_key="k1")
    assert other.code == "matrix", "same key from another actor is a different command"


class RacingStore(MemoryEventStore):
    """Lets a competing command land between load (step 3) and append (step 11), once."""

    def __init__(self, rival):
        super().__init__()
        self.rival, self.fired = rival, False

    def append(self, stream, expected_version, events):
        if not self.fired and events and events[0].kind == "domain" and not events[0].payload.get("fixture"):
            self.fired = True
            self.rival(self)
        return super().append(stream, expected_version, events)


def test_race_is_serialized_and_reevaluated():
    m_holder = {}

    def rival(store):
        out = m_holder["m"].interp.decide(Command(Actor("abe", "person", ("approver",)), "approve_experiment",
                                                  "E-onboarding", {}), project(store.read("E-onboarding")),
                                          m_holder["m"].lookup)
        MemoryEventStore.append(store, "E-onboarding", store.version("E-onboarding"), list(out.events))

    store = RacingStore(rival)
    m = ReferenceModel(domain(), store=store, clock=clock)
    m_holder["m"] = m
    out = do(m, ANA, "approve_experiment", "E-onboarding")
    assert out.code == "matrix", "the loser is re-evaluated and sees the approved state"
    assert m.state("E-onboarding")["approved_by"] == "abe"
    with pytest.raises(ConcurrencyError):
        store.append("E-onboarding", 1, [])


def test_replay_parity():
    m = model()
    do(m, ANA, "approve_experiment", "E-onboarding")
    out = do(m, ELI, "launch_experiment", "E-onboarding")
    assert project(m.store.read("E-onboarding")) == out.state == m.state("E-onboarding")


def test_paths_through_links_in_preconditions():
    def needs_statement(raw):
        raw["actions"]["approve_experiment"]["preconditions"].append(
            {"id": "has-statement", "check": "exists(target.hypothesis.statement)", "reason": "State the hypothesis."})
    m = model(needs_statement)
    assert do(m, ANA, "approve_experiment", "E-onboarding").ok


# -- regressions from review -------------------------------------------------------------------
def test_events_and_state_are_isolated_from_callers():
    m = model()
    s = m.state("E-onboarding")
    s["guardrails"].append("M-x")
    assert m.state("E-onboarding")["guardrails"] == ["M-latency"]
    params = {"note": "ok"}
    out = do(m, ANA, "approve_experiment", "E-onboarding", params=params)
    params["note"] = "changed"
    out.state["guardrails"].append("M-y")
    assert m.store.read("E-onboarding")[1].payload["params"] == {"note": "ok"}
    assert m.state("E-onboarding")["guardrails"] == ["M-latency"]


def test_create_effects_and_new_keys_fail_closed():
    def creates_effect(raw):
        raw["actions"]["approve_experiment"]["effects"].append({"create": "Readout"})
    assert do(model(creates_effect), ANA, "approve_experiment", "E-onboarding").code == "unsupported-effect"

    def new_key(raw):
        raw["actions"]["approve_experiment"]["effects"].append({"set": {"new.name": "actor.id"}})
    assert do(model(new_key), ANA, "approve_experiment", "E-onboarding").code == "unsupported-effect"


def test_by_role_is_order_independent_and_most_restrictive():
    def cell(raw):
        raw["actions"]["approve_experiment"]["actor"] = ["approver", "eng"]
        raw["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = {
            "by_role": {"approver": "approved", "eng": {"deny": "Engineers do not approve."}}}
    for roles in (("eng", "approver"), ("approver", "eng")):
        assert do(model(cell), Actor("x", "person", roles), "approve_experiment", "E-onboarding").code == "matrix"


def test_agent_cell_uses_principal_roles_too():
    def cell(raw):
        raw["actions"]["approve_experiment"]["actor"] = ["approver", "eng"]
        raw["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = {
            "by_role": {"approver": "approved", "eng": {"deny": "Engineers do not approve."}}}
    g = Grant("g", frozenset({"approve_experiment"}))
    out = do(model(cell), BOT, "approve_experiment", "E-onboarding", on_behalf_of=ELI, grant=g)
    assert out.code == "matrix", "an approver agent acting for an engineer gets the engineer's deny"


def test_principal_must_be_a_person():
    g = Grant("g", frozenset({"approve_experiment"}))
    sysadmin = Actor("root", "system", ("approver",))
    assert do(model(), BOT, "approve_experiment", "E-onboarding", on_behalf_of=sysadmin, grant=g).code == "actor"


def test_dangling_and_wrong_type_links_do_not_count():
    m = model()
    m.seed("Experiment", {"id": "E-dangle", "status": "draft", "guardrails": ["M-deleted", "H1"]})
    assert do(m, ANA, "approve_experiment", "E-dangle").code == "has-guardrails"


def test_allowed_actions_skip_params_dependent_checks():
    def needs_note(raw):
        raw["actions"]["approve_experiment"]["params"]["note"] = {"type": "string"}
        raw["actions"]["approve_experiment"]["preconditions"].append(
            {"id": "has-note", "check": "params.note != ''", "reason": "Say why."})
    m = model(needs_note)
    assert m.allowed_actions("E-onboarding", ANA) == ["approve_experiment"]
    assert do(m, ANA, "approve_experiment", "E-onboarding", params={"note": ""}).code == "has-note"


def test_type_of_comes_from_the_store():
    m = model()
    reloaded = ReferenceModel(m.d, store=m.store, clock=clock, seed_world=False)
    assert reloaded.type_of("E-onboarding") == "Experiment"
    assert reloaded.allowed_actions("E-onboarding", ANA) == ["approve_experiment"]


def test_idempotency_claims_and_transient_conflicts():
    m = model()
    key = ("ana", "approve_experiment", "E-onboarding", "k")
    assert m.store.claim(key) is None and m.store.claim(key) == "pending"
    assert do(m, ANA, "approve_experiment", "E-onboarding", idempotency_key="k").code == "in-progress"
    m.store.release(key)
    assert do(m, ANA, "approve_experiment", "E-onboarding", idempotency_key="k").ok


def test_invalid_params_and_missing_target():
    m = model()
    assert do(m, ANA, "approve_experiment", "E-onboarding", params={"note": 3}).code == "invalid-command"
    assert do(m, ANA, "approve_experiment", "E-onboarding", params={"bogus": 1}).code == "invalid-command"
    assert m.execute(Command(ANA, "approve_experiment", None)).code == "invalid-command"


def test_claim_is_released_when_evaluation_crashes():
    m = model()

    def boom(*a, **k):
        raise RuntimeError("store down")
    m.interp.decide, real = boom, m.interp.decide
    with pytest.raises(RuntimeError):
        do(m, ANA, "approve_experiment", "E-onboarding", idempotency_key="k")
    m.interp.decide = real
    assert do(m, ANA, "approve_experiment", "E-onboarding", idempotency_key="k").ok


def test_target_of_another_type_is_not_found():
    m = model()
    assert do(m, ANA, "approve_experiment", "H1").code == "not-found"
    assert m.store.version("H1") == 1


# -- ADR-0041 Resolved 4: actor.principal ------------------------------------------------------
def test_actor_principal_is_the_agents_principal_or_the_actor_itself():
    from toprope.semantics import Actor, Interpreter
    from test_decl import schema_doc_domain
    from toprope.decl import Domain
    it = Interpreter(Domain.model_validate(schema_doc_domain()))
    ana = Actor("ana", "person", ("approver",))
    bot = Actor("bot", "agent", ("approver",))
    env = lambda a, p=None: it._env({}, a, {}, principal=p).roots["actor"]            # noqa: E731
    assert env(ana)["principal"]["id"] == "ana"
    assert env(bot, ana)["principal"] == {"id": "ana", "kind": "person", "roles": ["approver"], "role": "approver"}
    assert env(bot)["principal"]["id"] == "bot"                    # an agent with no principal answers for itself
    assert env(ana, bot)["principal"]["id"] == "ana"               # only an agent has a principal
