"""Structured-output schema for the Gemini extraction step.

One schema covers every document type in the pack (flight tickets, hotel
vouchers/invoices, cab receipts, meal/entertainment bills, and the noise —
approval threads, advance notices, promos, payment-failure notices, third
party forwards). Gemini only ever fills this shape in; every rupee amount
downstream is then computed by app/services/policy_engine.py, never by the
model — see the plan's "Gemini extracts, Python decides" design note.
"""
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class PaymentMethodHint(str, Enum):
    CORPORATE_CARD = "corporate_card"
    PERSONAL_CARD = "personal_card"
    PAY_AT_HOTEL = "pay_at_hotel"
    CASH = "cash"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ExtractedDocType(str, Enum):
    TRAVEL_APPROVAL_REQUEST = "TRAVEL_APPROVAL_REQUEST"
    TRAVEL_APPROVAL_GRANTED = "TRAVEL_APPROVAL_GRANTED"
    ADVANCE_NOTICE = "ADVANCE_NOTICE"
    FLIGHT_TICKET = "FLIGHT_TICKET"
    HOTEL_VOUCHER = "HOTEL_VOUCHER"
    HOTEL_INVOICE = "HOTEL_INVOICE"
    CAB_RECEIPT = "CAB_RECEIPT"
    MEAL_BILL = "MEAL_BILL"
    BUSINESS_ENTERTAINMENT_BILL = "BUSINESS_ENTERTAINMENT_BILL"
    PAYMENT_FAILURE_NOTICE = "PAYMENT_FAILURE_NOTICE"
    THIRD_PARTY_FORWARD = "THIRD_PARTY_FORWARD"
    PROMOTIONAL_NOISE = "PROMOTIONAL_NOISE"
    OTHER = "OTHER"


class ExtractedLineItem(BaseModel):
    """One line inside an itemised bill (hotel folio, restaurant bill)."""

    label: str = Field(description="e.g. 'Room Charge', 'Laundry', 'Mini Bar', '2 x Paneer Tikka'")
    item_date: date | None = Field(default=None, description="Date this specific item was incurred, if shown")
    amount: float


class ExtractionResult(BaseModel):
    """Everything the model can plausibly read off one document."""

    doc_type: ExtractedDocType
    discard: bool = Field(
        description="True if this document is not a claimable expense at all "
        "(approval threads, advance notices, promo/marketing noise, a payment-failure "
        "notice, or an expense that clearly belongs to someone else)."
    )
    discard_reason: str | None = Field(
        default=None, description="Short reason if discard=True, e.g. 'promotional email, no transaction'"
    )

    traveler_name: str | None = Field(
        default=None,
        description="The person the receipt/greeting is addressed to or was booked for, "
        "e.g. 'Chaitanya' from 'Thanks for riding, Chaitanya'. Used to catch expenses "
        "that belong to a different employee.",
    )
    merchant: str | None = None
    city: str | None = None
    txn_date: date | None = None
    txn_time: str | None = Field(default=None, description="e.g. '05:20 AM' if shown")
    from_place: str | None = None
    to_place: str | None = None
    bill_number: str | None = None
    payment_method: PaymentMethodHint = PaymentMethodHint.UNKNOWN

    gross_amount: float | None = Field(
        default=None, description="Total amount on the document, for simple single-amount receipts"
    )
    line_items: list[ExtractedLineItem] = Field(
        default_factory=list, description="Itemised breakdown for hotel folios / restaurant bills"
    )
    subtotal: float | None = None
    tax_total: float | None = None

    # Lodging-specific
    check_in: date | None = None
    check_out: date | None = None
    nights: int | None = None
    room_tariff_per_night: float | None = None

    # Business entertainment-specific
    attendee_count: int | None = None
    attendee_names: list[str] = Field(default_factory=list)
    attendee_org: str | None = None

    confidence: float = Field(default=0.8, ge=0, le=1)
