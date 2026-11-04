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


def test_real_race_between_connections(open_store, store_kind):
    if store_kind == "memory":
        pytest.skip("needs two connections to one database")
    a, b = open_store(), open_store()
    results, barrier = [], threading.Barrier(2)

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
