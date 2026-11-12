import os
import uuid

import pytest

from toprope.store import MemoryEventStore

PG_DSN = os.environ.get("TOPROPE_PG_DSN")
KINDS = ["memory", "sqlite", "jsonl"] + (["postgres"] if PG_DSN else [])


@pytest.fixture(params=KINDS)
def store_kind(request):
    return request.param


@pytest.fixture
def open_store(store_kind, tmp_path):
    """Returns open() -> a new store instance on the SAME underlying database (for races and
    reopen tests). Memory stores cannot share state, so they return the same instance."""
    made = []
    schema = f"t_{uuid.uuid4().hex[:12]}"
    mem = MemoryEventStore()

    def open_():
        if store_kind == "memory":
            return mem
        if store_kind == "sqlite":
            from toprope.store.sqlite import SQLiteEventStore
            s = SQLiteEventStore(str(tmp_path / "events.db"))
        elif store_kind == "jsonl":
            from toprope.store.jsonl import JSONLEventStore
            s = JSONLEventStore(tmp_path / "events")
        else:
            from toprope.store.postgres import PostgresEventStore
            s = PostgresEventStore(PG_DSN, schema=schema)
        made.append(s)
        return s

    yield open_
    for s in made:
        s.close()
    if store_kind == "postgres" and made:
        import psycopg
        with psycopg.connect(PG_DSN, autocommit=True) as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


# Under pytest-xdist (`pytest -n auto`, as CI runs it): a module whose module fixture is costly
# goes to one worker as a whole, so the fixture is built once; every other test is scheduled on
# its own, so the workers stay evenly loaded. `--dist loadgroup` would do the first part, but its
# group marks do not take with the pytest this project pins.
SHARED_FIXTURE_MODULES = ("tests/test_phase_b_probes.py",)   # the eight probe worlds, ~4 minutes


def pytest_xdist_make_scheduler(config, log):
    from xdist.scheduler import LoadScopeScheduling

    class OneWorkerForCostlyModules(LoadScopeScheduling):
        def _split_scope(self, nodeid: str) -> str:
            module = nodeid.split("::", 1)[0]
            return module if module.endswith(SHARED_FIXTURE_MODULES) else nodeid

    return OneWorkerForCostlyModules(config, log)
