import os
import uuid

import pytest

from toprope.store import MemoryEventStore

PG_DSN = os.environ.get("TOPROPE_PG_DSN")
KINDS = ["memory", "sqlite"] + (["postgres"] if PG_DSN else [])


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
