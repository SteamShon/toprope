from datetime import datetime, timedelta, timezone

from test_decl import schema_doc_domain
from test_semantics import MATRIX_CODES
from toprope.decl import Domain
from toprope.exec import Execution
from toprope.identity import Caller, StaticIdentity
from toprope.semantics import Actor, Grant

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
ANA = Actor("ana", "person", ("approver",))
ELI = Actor("eli", "person", ("eng",))
PAT = Actor("pat", "person", ("pm",))
BOT = Actor("bot", "agent", ("approver",))
IDS = StaticIdentity({
    "t-ana": Caller(ANA), "t-eli": Caller(ELI), "t-pat": Caller(PAT),
    "t-bot": Caller(BOT, ANA, Grant("g1", frozenset({"approve_experiment"}), expires_at=NOW + timedelta(hours=1))),
})


def execution(store) -> Execution:
    ex = Execution(Domain.model_validate(schema_doc_domain()), store, IDS, clock=lambda: NOW)
    ex.seed_world()
    return ex


def test_unauthenticated_and_identity(open_store):
    ex = execution(open_store())
    assert ex.submit(None, "approve_experiment", "E-onboarding").code == "unauthenticated"
    assert ex.submit("t-nobody", "approve_experiment", "E-onboarding").code == "unauthenticated"
    out = ex.submit("t-bot", "approve_experiment", "E-onboarding", thread_id="th")
    assert out.ok and out.events[0].on_behalf_of == {"id": "ana", "kind": "person"}
    assert ex.history("E-onboarding")[-2].grant == "g1"


def test_schema_doc_flow_on_every_store(open_store):
    ex = execution(open_store())
    assert ex.allowed_actions("E-onboarding", PAT) == []
    assert ex.submit("t-eli", "launch_experiment", "E-onboarding").code in MATRIX_CODES
    assert ex.submit("t-ana", "approve_experiment", "E-onboarding", {"note": "ok"}).ok
    assert ex.allowed_actions("E-onboarding", ELI) == ["launch_experiment"]
    out = ex.submit("t-eli", "launch_experiment", "E-onboarding")
    assert out.ok and ex.state("E-onboarding")["status"] == "running"
    assert ex.submit("t-ana", "approve_experiment", "E-bare").code == "has-guardrails"
    assert [a.payload["code"] for a in ex.attempts("E-onboarding")][0] == "matrix"


def test_seed_world_is_idempotent(open_store):
    ex = execution(open_store())
    assert ex.seed_world() == 0


def test_idempotent_submit_survives_reopen(open_store, store_kind):
    s = open_store()
    ex = execution(s)
    first = ex.submit("t-ana", "approve_experiment", "E-onboarding", idempotency_key="k")
    again = execution(open_store()).submit("t-ana", "approve_experiment", "E-onboarding", idempotency_key="k")
    assert first.ok and again.ok and again.state == first.state
    assert s.version("E-onboarding") == 3, "no second append"


def test_two_executions_race_on_one_cell(open_store, store_kind):
    import threading
    if store_kind == "memory":
        return
    a, b = execution(open_store()), execution(open_store())
    callers = {"t-ana": a, "t-abe": b}
    IDS._callers["t-abe"] = Caller(Actor("abe", "person", ("approver",)))
    outs, barrier = {}, threading.Barrier(2)

    def go(token):
        barrier.wait()
        outs[token] = callers[token].submit(token, "approve_experiment", "E-onboarding")

    ts = [threading.Thread(target=go, args=(t,)) for t in callers]
    [t.start() for t in ts]
    [t.join() for t in ts]
    codes = sorted((o.code or "ok") for o in outs.values())
    assert codes == ["matrix", "ok"], codes
    assert a.state("E-onboarding")["status"] == "approved"
