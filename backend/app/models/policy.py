"""Policy-as-data tables, seeded from expense_policy.md so the numbers in the
policy engine are configuration, not constants buried in Python.
"""
from __future__ import annotations

from sqlalchemy import JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CityTier(Base):
    """Policy 3.1 — city -> tier, drives lodging and meal caps."""

    __tablename__ = "city_tier"

    city: Mapped[str] = mapped_column(String(64), primary_key=True)
    tier: Mapped[int] = mapped_column()  # 1, 2, or 3


class PolicyConfig(Base):
    """Single-row-per-key policy config: caps, thresholds, windows.

    Kept as a generic key/value table (value stored as text, parsed by the
    caller) rather than dozens of typed columns, since these numbers change
    per policy revision and a config table survives that without a migration.
    """

    __tablename__ = "policy_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255))


class ApprovalBand(Base):
    """Policy 2 matrix: value band -> ordered list of required approval levels.

    required_levels is an ordered JSON array of role codes, e.g.
    ["REPORTING_MANAGER", "HOD"]. FINANCE is intentionally never included here
    — it is appended unconditionally by the routing engine per policy 2.1.
    """

    __tablename__ = "approval_band"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    min_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    max_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    international_only: Mapped[bool] = mapped_column(default=False)
    required_levels: Mapped[list] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(String(255))
