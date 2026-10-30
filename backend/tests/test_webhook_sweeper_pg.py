"""PostgreSQL row-lock concurrency test for webhook sweeper claiming.

Skipped unless TEACHFLOW_TEST_DATABASE_URL points at PostgreSQL. SQLite tests
do not prove SELECT ... FOR UPDATE SKIP LOCKED behaviour.
"""
from __future__ import annotations

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import webhook_sweeper  # noqa: E402
from src.database import Base, PaystackWebhookEventDB, generate_id  # noqa: E402

PG_URL = os.environ.get("TEACHFLOW_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not PG_URL.startswith("postgres"),
    reason="PostgreSQL test URL not configured",
)


def test_two_workers_cannot_claim_the_same_event():
    engine = create_engine(PG_URL)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    setup = Session()
    try:
        row = PaystackWebhookEventDB(
            id=generate_id(),
            event_key=f"pg-claim:{generate_id()}",
            event_type="bank.transfer.rejected",
            reference="PG-CLAIM",
            payload_json={"reference": "PG-CLAIM", "status": "failed"},
            status="received",
            attempts=0,
            received_at=datetime.utcnow() - timedelta(minutes=10),
        )
        setup.add(row)
        setup.commit()
        event_id = row.id
    finally:
        setup.close()

    barrier = threading.Barrier(2)

    def claim(worker):
        session = Session()
        try:
            barrier.wait(timeout=10)
            return [r.id for r in webhook_sweeper.claim_events(
                session, batch_size=1, worker_id=worker)]
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["worker-a", "worker-b"]))

    assert sorted(len(result) for result in results) == [0, 1]
    check = Session()
    try:
        stored = check.query(PaystackWebhookEventDB).filter_by(
            id=event_id).one()
        assert stored.status == "processing"
        assert stored.lease_owner in ("worker-a", "worker-b")
        assert stored.attempts == 1
    finally:
        check.close()
        engine.dispose()
