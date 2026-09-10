"""Source documents: the 15 seeded .eml files and 2 receipt PNGs, plus any
future uploads. claim_line.proof_ref points here so the settlement form's
"Proof Ref must point at a specific supporting document" rule (legend B65)
is enforced by a foreign key, not a free-text convention.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import DocType, ExtractionMode


class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(ForeignKey("employee.emp_code"))
    travel_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("travel_request.id"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(64))
    sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    doc_type: Mapped[DocType | None] = mapped_column(String(48), nullable=True)
    extraction_mode: Mapped[ExtractionMode | None] = mapped_column(String(24), nullable=True)
    extraction_raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    discarded: Mapped[bool] = mapped_column(default=False)
    discard_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim_lines: Mapped[list["ClaimLine"]] = relationship(back_populates="proof_document")  # noqa: F821
