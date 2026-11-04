"""Every EventStore adapter satisfies the same contract (ADR-0012, docs/semantics.md §2-§5)."""
import threading
from datetime import datetime, timezone

import pytest

from toprope.semantics.types import Event, Outcome
from toprope.store import ConcurrencyError

AT = datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)


def ev(stream="S1", kind="domain", **payload):
    return Event("Thing", stream, "Obj", at=AT, actor={"id": "ana", "kind": "person"},
                 payload={"changes": payload or {"x": 1}, "nested": {"list": [1, {"a": None}]}},
                 kind=kind, domain_version=3, thread_id="t1")


def test_append_read_roundtrip(open_store):
    s = open_store()
    out = s.append("S1", 0, [ev(), ev(kind="decision")])
    assert [e.version for e in out] == [1, 2] and s.version("S1") == 2
    back = s.read("S1")
    assert back == out
    assert back[0].at == AT and back[0].payload["nested"] == {"list": [1, {"a": None}]}


def test_stale_version_is_a_concurrency_error(open_store):
    s = open_store()
    s.append("S1", 0, [ev()])
    with pytest.raises(ConcurrencyError):
        s.append("S1", 0, [ev()])
    assert s.version("S1") == 1


def test_attempts_never_bump_versions(open_store):
    s = open_store()
    s.append_attempt(ev(kind="attempt"))
    s.append_attempt(ev(kind="attempt"))
    assert s.version("S1") == 0 and len(s.read_attempts("S1")) == 2 and s.read("S1") == []


def test_streams_in_creation_order(open_store):
    s = open_store()
    s.append("B", 0, [ev("B")])
    s.append("A", 0, [ev("A")])
    s.append("B", 1, [ev("B")])
    assert s.streams() == ["B", "A"]


def test_idempotency_claim_remember_release(open_store):
    s = open_store()
    k = ("ana", "approve", "E1", "k1")
    assert s.claim(k) is None
    assert s.claim(k) == "pending"
    s.release(k)
    assert s.claim(k) is None
    out = Outcome("ok", state={"status": "approved"}, events=(ev(),))
    s.remember(k, out)
    got = s.claim(k)
    assert isinstance(got, Outcome) and got.state == {"status": "approved"} and got.events[0].at == AT
    s.release(k)  # releasing a finished key does nothing
    assert isinstance(s.claim(k), Outcome)


def test_durable_across_reopen(open_store, store_kind):
    if store_kind == "memory":
        pytest.skip("memory store is not durable")
    a = open_store()
    a.append("S1", 0, [ev()])
    a.remember(("k",), Outcome("ok")) if a.claim(("k",)) is None else None
    b = open_store()
    assert b.version("S1") == 1 and b.read("S1")[0].payload["changes"] == {"x": 1}
    assert isinstance(b.claim(("k",)), Outcome)


def _force_interleave(store, gate):
    """Make append's version check wait until the other thread has also checked (or until the
    database serializes us), so both threads really pass the check before either inserts."""
    real = store.version

    def version(stream):
        v = real(stream)
        try:
            gate.wait(timeout=1.0)   # times out if the store serializes appends (fine)
        except threading.BrokenBarrierError:
            pass
        return v
    store.version = version


def test_real_race_between_connections(open_store, store_kind):
    if store_kind == "memory":
        pytest.skip("needs two connections to one database")
    a, b = open_store(), open_store()
    results, barrier, gate = [], threading.Barrier(2), threading.Barrier(2)
    for s in (a, b):
        _force_interleave(s, gate)

    def go(store):
        barrier.wait()
        try:
            store.append("R", 0, [ev("R")])
            results.append("ok")
        except ConcurrencyError:
            results.append("conflict")

    ts = [threading.Thread(target=go, args=(x,)) for x in (a, b)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(results) == ["conflict", "ok"] and a.version("R") == 1


def test_real_claim_race_between_connections(open_store, store_kind):
    if store_kind == "memory":
        pytest.skip("needs two connections to one database")
    a, b = open_store(), open_store()
    got, barrier = [], threading.Barrier(2)

    def go(store):
        barrier.wait()
        got.append(store.claim(("race",)))

    ts = [threading.Thread(target=go, args=(x,)) for x in (a, b)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(map(str, got)) == ["None", "pending"]


def test_codec_is_unambiguous_and_identical_across_stores(open_store):
    from datetime import date
    s = open_store()
    tricky = {"$dt": "not a date", "$$x": 1, "d": date(2026, 1, 2), "t": (1, 2)}
    s.append("C", 0, [ev("C", **tricky)])
    assert s.read("C")[0].payload["changes"] == {"$dt": "not a date", "$$x": 1, "d": date(2026, 1, 2), "t": [1, 2]}


@pytest.mark.parametrize("bad", [float("nan"), "a\x00b"])
def test_unstorable_values_fail_before_writing(open_store, bad):
    from toprope.store.codec import CodecError
    s = open_store()
    with pytest.raises(CodecError):
        s.append("N", 0, [ev("N", x=bad)])
    assert s.version("N") == 0


def test_shared_instance_is_thread_safe(open_store, store_kind):
    """Threads sharing one instance: a failing append must not swallow another thread's write."""
    s = open_store()
    s.append("T", 0, [ev("T")])
    errors = []

    def failing_appends():
        for _ in range(50):
            try:
                s.append("T", 0, [ev("T")])   # always stale -> ConcurrencyError + rollback
            except ConcurrencyError:
                pass

    def attempts():
        for _ in range(50):
            try:
                s.append_attempt(ev("T", kind="attempt"))
            except Exception as e:  # pragma: no cover
                errors.append(e)

    ts = [threading.Thread(target=failing_appends), threading.Thread(target=attempts)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors and len(s.read_attempts("T")) == 50 and s.version("T") == 1
