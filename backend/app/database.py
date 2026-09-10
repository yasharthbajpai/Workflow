"""Engine, session factory, and declarative base bound to the Sample_test schema.

Sample_test is mixed-case, so Postgres requires it to be quoted everywhere or it
silently folds to sample_test. Binding schema=settings.db_schema on MetaData makes
SQLAlchemy quote it automatically on every DDL/DML statement it emits, and
ensure_schema() creates it (quoted) before anything else touches the database.
"""
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.sqlalchemy_database_uri, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

metadata = MetaData(schema=settings.db_schema)


class Base(DeclarativeBase):
    metadata = metadata


def ensure_schema() -> None:
    """CREATE SCHEMA IF NOT EXISTS "Sample_test" — must run before create_all()."""
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
