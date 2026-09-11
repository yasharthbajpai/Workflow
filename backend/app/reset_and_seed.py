"""Drop the demo schema and seed it from scratch.

Use this when you want a first-login database: no leftover claims, no
cached extractions, Chaitanya's Bengaluru trip ready to scan, and Imran's
Hyderabad inbox waiting to be attached to a new Travel Request.

  backend/.venv/bin/python -m app.reset_and_seed

Also invoked from render_start.sh when RESET_DEMO_DATA=1 so a deploy starts
the same way.
"""
from __future__ import annotations

from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal, engine, ensure_schema
from app.models import Document, Employee, TravelRequest
from app.seed import run


def reset_demo_schema() -> None:
    smoke = f"{settings.db_schema}_smoke"
    engine.dispose()
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{settings.db_schema}" CASCADE'))
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{smoke}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{settings.db_schema}"'))
    print(f'Dropped and recreated schema "{settings.db_schema}".')


def migrate() -> None:
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    print("Migrations applied.")


def report() -> None:
    db = SessionLocal()
    try:
        employees = db.query(Employee).count()
        trs = db.query(TravelRequest).all()
        print(f"Employees: {employees}")
        for tr in trs:
            n = db.query(Document).filter(Document.travel_request_id == tr.id).count()
            print(f"  {tr.travel_request_no} ({tr.employee_code}) — {n} documents")
        unlinked = (
            db.query(Document.employee_code, Document.id)
            .filter(Document.travel_request_id.is_(None))
            .all()
        )
        by_emp: dict[str, int] = {}
        for emp_code, _ in unlinked:
            by_emp[emp_code] = by_emp.get(emp_code, 0) + 1
        for emp_code, n in sorted(by_emp.items()):
            print(f"  Unlinked inbox for {emp_code}: {n} documents (attach on new TR)")
    finally:
        db.close()


def main() -> None:
    reset_demo_schema()
    ensure_schema()
    migrate()
    run()
    report()


if __name__ == "__main__":
    main()
