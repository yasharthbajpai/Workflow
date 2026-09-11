"""Claim + claim_line + line_policy_flag — Travel Expense Settlement Form
(NTX-SET-02) and its policy verdicts.

claim_line carries both sides of every judgement (legend B66: disallowed
items go on a disallowed line with a reason, never dropped), and every money
total downstream is a deterministic function of these rows, never a model
output — see PLAN "Core design decision: Bedrock extracts, Python decides".
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ClaimSection, ClaimStatus, ExtractionMode, FlagSeverity, PaidBy


class Claim(Base):
    __tablename__ = "claim"

    id: Mapped[int] = mapped_column(primary_key=True)
    travel_request_id: Mapped[int] = mapped_column(ForeignKey("travel_request.id"))
    employee_code: Mapped[str] = mapped_column(ForeignKey("employee.emp_code"))
    status: Mapped[ClaimStatus] = mapped_column(String(32), default=ClaimStatus.DRAFT)
    submission_no: Mapped[int] = mapped_column(default=1)  # increments on every 2.3 resubmission
    cycle_no: Mapped[int] = mapped_column(default=1)  # approval_step rows are scoped to this
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Settlement summary (Section 4 of NTX-SET-02) — computed by the policy
    # engine, never hand-entered.
    total_employee_paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_company_paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_disallowed: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    net_reimbursable: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    advance_drawn: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    amount_payable: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    amount_recoverable: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    travel_request: Mapped["TravelRequest"] = relationship(back_populates="claims")  # noqa: F821
    employee: Mapped["Employee"] = relationship()  # noqa: F821
    lines: Mapped[list["ClaimLine"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="ClaimLine.id"
    )
    approval_steps: Mapped[list["ApprovalStep"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan", order_by="ApprovalStep.cycle_no, ApprovalStep.sequence"
    )
    events: Mapped[list["ClaimEvent"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan", order_by="ClaimEvent.created_at"
    )
    payment: Mapped["Payment | None"] = relationship(  # noqa: F821
        back_populates="claim", uselist=False, cascade="all, delete-orphan"
    )


class ClaimLine(Base):
    __tablename__ = "claim_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claim.id"))
    section: Mapped[ClaimSection] = mapped_column(String(16))  # LODGING | TRANSPORT | OTHER
    head: Mapped[str] = mapped_column(String(64))  # e.g. Lodging, Cab, Meals, Business Entertainment
    txn_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(255))
    merchant: Mapped[str | None] = mapped_column(String(128), nullable=True)
    from_place: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_place: Mapped[str | None] = mapped_column(String(128), nullable=True)

    gross_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    allowed_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    disallowed_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    disallowed_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    paid_by: Mapped[PaidBy] = mapped_column(String(16), default=PaidBy.EMPLOYEE)
    proof_document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id"), nullable=True)
    proof_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source: Mapped[ExtractionMode] = mapped_column(String(24), default=ExtractionMode.MANUAL)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)  # e.g. duplicate / third-party
    duplicate_of_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("claim_line.id"), nullable=True
    )
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # attendees etc.

    claim: Mapped["Claim"] = relationship(back_populates="lines")
    proof_document: Mapped["Document | None"] = relationship(back_populates="claim_lines")  # noqa: F821
    flags: Mapped[list["LinePolicyFlag"]] = relationship(
        back_populates="claim_line", cascade="all, delete-orphan"
    )


class LinePolicyFlag(Base):
    __tablename__ = "line_policy_flag"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_line_id: Mapped[int] = mapped_column(ForeignKey("claim_line.id"))
    code: Mapped[str] = mapped_column(String(48))  # e.g. LODGING_TARIFF_EXCESS
    severity: Mapped[FlagSeverity] = mapped_column(String(8))
    policy_ref: Mapped[str] = mapped_column(String(16))  # e.g. "3.1", "5.3"
    message: Mapped[str] = mapped_column(String(500))

    claim_line: Mapped["ClaimLine"] = relationship(back_populates="flags")
