"""approval_step, claim_event, payment.

approval_step rows are never deleted or overwritten on a 2.3 return/resubmit
cycle — cycle_no scopes each resubmission's steps so the full history stays
visible in the <ApprovalProgress> timeline.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.enums import ApprovalStepStatus, ApprovalStepType, PaymentStatus
from app.database import Base


class ApprovalStep(Base):
    __tablename__ = "approval_step"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claim.id"))
    cycle_no: Mapped[int] = mapped_column(default=1)
    sequence: Mapped[int] = mapped_column()  # order within the cycle, 1-based
    step_type: Mapped[ApprovalStepType] = mapped_column(String(24))
    role_code: Mapped[str] = mapped_column(ForeignKey("app_role.code"))
    assigned_to_code: Mapped[str | None] = mapped_column(
        ForeignKey("employee.emp_code"), nullable=True
    )
    status: Mapped[ApprovalStepStatus] = mapped_column(String(16), default=ApprovalStepStatus.PENDING)
    skip_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # policy 2.2
    remarks: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped["Claim"] = relationship(back_populates="approval_steps")  # noqa: F821
    assigned_to: Mapped["Employee | None"] = relationship()  # noqa: F821


class ClaimEvent(Base):
    """Append-only audit trail: submit, approve, return, reject, verify, pay."""

    __tablename__ = "claim_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claim.id"))
    actor_code: Mapped[str | None] = mapped_column(ForeignKey("employee.emp_code"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped["Claim"] = relationship(back_populates="events")  # noqa: F821
    actor: Mapped["Employee | None"] = relationship()  # noqa: F821


class Payment(Base):
    """Finance payment run — processed on the 10th/25th per policy 5.4."""

    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claim.id"), unique=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    scheduled_run_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(String(16), default=PaymentStatus.SCHEDULED)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(64), nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="payment")  # noqa: F821
