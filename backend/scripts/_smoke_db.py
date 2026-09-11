"""Isolated database session for the standalone verification scripts.

scripts/smoke_test_policy_engine.py and scripts/smoke_test_workflow.py need
real employees, policy config, and city tiers to exercise the real
routing/policy code paths — but backend/.env's DATABASE_URL points at the
same Postgres the running app/demo uses, and both scripts ultimately call
functions (build_or_refresh_claim, workflow.submit_claim/approve_step/...)
that call db.commit() internally. Running them against SessionLocal would
therefore permanently: (a) overwrite the seeded documents' extraction_raw_json
with hand-authored fixture JSON, so "Scan my inbox" replays canned data
forever instead of re-invoking Bedrock, and (b) create/pay a fake claim
(Suresh Iyer's TRQ-2026-9001) that would show up in Approvals/Finance/
Dashboard for anyone demoing the live app.

Fix: every smoke-test session below is bound to a *sibling* schema
("<DB_SCHEMA>_smoke") on the same database, via SQLAlchemy's
schema_translate_map — every model/query/commit in policy_engine.py,
workflow.py, routing.py, and claim_builder.py is unaffected and none of it
needs to know this schema even exists. The smoke schema is dropped and
recreated fresh on every run and seeded independently, so it never reads or
writes a single row of the real "<DB_SCHEMA>" schema.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import Base, engine

SMOKE_SCHEMA = f"{settings.db_schema}_smoke"

_smoke_engine = engine.execution_options(schema_translate_map={settings.db_schema: SMOKE_SCHEMA})
SmokeSessionLocal = sessionmaker(bind=_smoke_engine, autoflush=False, autocommit=False, future=True)


def reset_smoke_schema() -> None:
    """Drop (if present) and recreate the smoke schema plus every table, so
    each run starts from a clean slate — never touching settings.db_schema.
    """
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{SMOKE_SCHEMA}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{SMOKE_SCHEMA}"'))
    Base.metadata.create_all(bind=_smoke_engine)


def smoke_session() -> Session:
    return SmokeSessionLocal()
