"""Travel request + estimate + advance — Travel Request Form (NTX-TRF-02)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import TravelRequestStatus


class TravelRequest(Base):
    __tablename__ = "travel_request"

    id: Mapped[int] = mapped_column(primary_key=True)
    travel_request_no: Mapped[str] = mapped_column(String(32), unique=True)  # TRQ-2026-0000
    employee_code: Mapped[str] = mapped_column(ForeignKey("employee.emp_code"))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    visiting_place: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(64))  # normalised city for tier lookup
    purpose: Mapped[str] = mapped_column(String(255))
    mode_of_travel: Mapped[str] = mapped_column(String(64))
    is_international: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    advance_requested: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[TravelRequestStatus] = mapped_column(
        String(32), default=TravelRequestStatus.PENDING_APPROVAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employee: Mapped["Employee"] = relationship()  # noqa: F821
    estimate_lines: Mapped[list["EstimateLine"]] = relationship(
        back_populates="travel_request", cascade="all, delete-orphan"
    )
    advance: Mapped["Advance | None"] = relationship(
        back_populates="travel_request", uselist=False, cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(back_populates="travel_request")  # noqa: F821


class EstimateLine(Base):
    __tablename__ = "estimate_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    travel_request_id: Mapped[int] = mapped_column(ForeignKey("travel_request.id"))
    head: Mapped[str] = mapped_column(String(64))  # Air/Rail, Lodging, Local conveyance, Meals, Other
    basis: Mapped[str] = mapped_column(String(128))
    estimate: Mapped[float] = mapped_column(Numeric(12, 2))
    borne_by: Mapped[str] = mapped_column(String(16))  # Employee | Company

    travel_request: Mapped["TravelRequest"] = relationship(back_populates="estimate_lines")


class Advance(Base):
    __tablename__ = "advance"

    id: Mapped[int] = mapped_column(primary_key=True)
    travel_request_id: Mapped[int] = mapped_column(ForeignKey("travel_request.id"), unique=True)
    reference: Mapped[str] = mapped_column(String(64))  # e.g. ADV/2026/0619
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    disbursed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    travel_request: Mapped["TravelRequest"] = relationship(back_populates="advance")
