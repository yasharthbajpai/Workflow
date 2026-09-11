"""Turns one Document (an .eml's text, or a receipt image) into an
ExtractionResult.

Primary path: AWS Bedrock (BEDROCK_MODEL_ID from env, e.g. an Anthropic Claude
model id) via the model-agnostic Converse API, with a forced tool-use call so
the response is pinned to the ExtractionResult JSON schema instead of a string
the app would have to hand-parse.

Fallback path: a small set of regex parsers for the three known senders in
this pack (Uber, MakeMyTrip, hotel/restaurant tax invoices), used when
BEDROCK_MODEL_ID is unset or the API call raises/times out, so a demo never
hard-fails on a throttling error or missing credentials. Document.extraction_mode
records which path ran.
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import date, datetime

from app.config import settings
from app.models import Document
from app.models.enums import ExtractionMode
from app.schemas.extraction import ExtractedDocType, ExtractedLineItem, ExtractionResult, PaymentMethodHint

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expense-document parser for an Indian company's travel desk.
You will be shown the text (or image) of ONE email or receipt from an employee's inbox.
Extract it into the given JSON schema exactly, by calling the extract_expense_document tool. Rules:
- If the message is a travel-approval thread, an advance-disbursement notice, a marketing/promo
  email, or otherwise not a specific claimable transaction, set discard=true with a short reason.
- If a payment failed (e.g. "Payment failed", "We could not charge your card"), set
  doc_type=PAYMENT_FAILURE_NOTICE and discard=true — it is not a valid expense.
- If the receipt greeting or booking name refers to someone other than the account owner
  (e.g. "Thanks for riding, Deepa" when the inbox owner is someone else, or an explicit
  forward asking to add another person's expense), set traveler_name to that other person's
  name and doc_type=THIRD_PARTY_FORWARD.
- For itemised bills (hotel folios, restaurant bills) populate line_items with every line,
  plus subtotal and tax_total exactly as printed. Do not compute or apportion anything yourself.
- For business entertainment / hosted meals, extract attendee_count and any attendee names or
  organisation mentioned, even if incomplete.
- Never invent numbers. If a field is not present in the document, leave it null/empty.
"""

_TOOL_NAME = "extract_expense_document"

_client = None
_client_lock = threading.Lock()


def _get_client():
    """Thread-safe singleton bedrock-runtime client, built once and reused."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                import boto3

                kwargs: dict[str, str] = {"region_name": settings.aws_region}
                if settings.aws_access_key_id and settings.aws_secret_access_key:
                    kwargs["aws_access_key_id"] = settings.aws_access_key_id
                    kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
                _client = boto3.client("bedrock-runtime", **kwargs)
    return _client


def _tool_config() -> dict:
    # Pydantic's JSON schema (incl. $defs for ExtractedLineItem/enums) is
    # passed straight through as the tool's inputSchema — Bedrock's Converse
    # API forwards it to the underlying model's native tool-use format.
    schema = ExtractionResult.model_json_schema()
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": _TOOL_NAME,
                    "description": "Extract structured fields from one expense-related email or receipt.",
                    "inputSchema": {"json": schema},
                }
            }
        ],
        "toolChoice": {"tool": {"name": _TOOL_NAME}},
    }


def extract_document(document: Document) -> tuple[ExtractionResult, ExtractionMode]:
    if settings.bedrock_model_id:
        try:
            result = _extract_with_bedrock(document)
            return result, ExtractionMode.BEDROCK
        except Exception:  # noqa: BLE001 — any SDK/network/credentials failure falls back
            logger.exception("Bedrock extraction failed for document %s, falling back to regex", document.id)
    result = _extract_with_regex(document)
    return result, ExtractionMode.REGEX_FALLBACK


def _image_format(mime_type: str | None) -> str:
    fmt = (mime_type or "image/png").split("/")[-1].lower()
    return "jpeg" if fmt == "jpg" else fmt


def _extract_with_bedrock(document: Document) -> ExtractionResult:
    client = _get_client()

    if document.image_bytes:
        content = [
            {"image": {"format": _image_format(document.mime_type), "source": {"bytes": document.image_bytes}}},
            {"text": f"Filename: {document.filename}\nSubject: {document.subject or ''}"},
        ]
    else:
        content = [
            {
                "text": (
                    f"From: {document.sender or ''}\nSubject: {document.subject or ''}\n\n"
                    f"{document.raw_text or ''}"
                )
            }
        ]

    response = client.converse(
        modelId=settings.bedrock_model_id,
        system=[{"text": _SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": content}],
        toolConfig=_tool_config(),
    )

    for block in response["output"]["message"]["content"]:
        tool_use = block.get("toolUse")
        if tool_use and tool_use.get("name") == _TOOL_NAME:
            return ExtractionResult.model_validate(tool_use["input"])

    raise ValueError("Bedrock response did not include the expected tool_use block")


# --- Regex fallback ----------------------------------------------------------

_AMOUNT_RE = re.compile(r"([\d,]+\.\d{2})")


def _to_amount(text: str) -> float | None:
    m = _AMOUNT_RE.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def _extract_with_regex(document: Document) -> ExtractionResult:
    text = document.raw_text or ""
    sender = (document.sender or "").lower()
    subject = (document.subject or "").lower()

    if document.image_bytes and not text:
        # Regex fallback cannot OCR an image; hand back a low-confidence,
        # needs-review placeholder rather than fail outright.
        return ExtractionResult(
            doc_type=ExtractedDocType.OTHER,
            discard=False,
            merchant=document.subject,
            confidence=0.1,
        )

    if "uber" in sender:
        return _extract_uber(text)
    if "makemytrip" in sender:
        return _extract_makemytrip(text, subject)
    if "offers@" in sender or "promo" in subject or "% off" in text.lower():
        return ExtractionResult(
            doc_type=ExtractedDocType.PROMOTIONAL_NOISE, discard=True, discard_reason="Promotional/marketing email"
        )
    if "finance" in sender and "advance" in subject:
        return ExtractionResult(
            doc_type=ExtractedDocType.ADVANCE_NOTICE, discard=True, discard_reason="Advance disbursement notice, not a claim line"
        )
    if "travel approval" in subject or "approval request" in subject:
        return ExtractionResult(
            doc_type=ExtractedDocType.TRAVEL_APPROVAL_GRANTED
            if "re:" in subject
            else ExtractedDocType.TRAVEL_APPROVAL_REQUEST,
            discard=True,
            discard_reason="Approval thread, not a claim line",
        )
    if "fwd:" in subject and "uber" in text.lower():
        return _extract_third_party_forward(text)

    return ExtractionResult(doc_type=ExtractedDocType.OTHER, discard=False, confidence=0.2)


def _extract_uber(text: str) -> ExtractionResult:
    if "payment failed" in text.lower() or "could not charge" in text.lower():
        amount = _to_amount(text)
        return ExtractionResult(
            doc_type=ExtractedDocType.PAYMENT_FAILURE_NOTICE,
            discard=True,
            discard_reason="Payment failed — no completed transaction",
            gross_amount=amount,
        )

    amount = _to_amount(text)
    pickup = re.search(r"Pickup\s+(.+)", text)
    drop = re.search(r"Drop\s+(.+)", text)
    date_m = re.search(r"(\d{1,2} \w{3} \d{4})", text)
    greet = re.search(r"riding,\s*(\w+)", text)
    txn_date = None
    if date_m:
        try:
            txn_date = datetime.strptime(date_m.group(1), "%d %b %Y").date()
        except ValueError:
            txn_date = None
    return ExtractionResult(
        doc_type=ExtractedDocType.CAB_RECEIPT,
        discard=False,
        merchant="Uber",
        traveler_name=greet.group(1) if greet else None,
        txn_date=txn_date,
        from_place=pickup.group(1).strip() if pickup else None,
        to_place=drop.group(1).strip() if drop else None,
        gross_amount=amount,
        payment_method=PaymentMethodHint.PERSONAL_CARD if "personal" in text.lower() else PaymentMethodHint.UNKNOWN,
        confidence=0.75,
    )


def _extract_third_party_forward(text: str) -> ExtractionResult:
    amount = _to_amount(text)
    greet = re.search(r"riding,\s*(\w+)", text)
    return ExtractionResult(
        doc_type=ExtractedDocType.THIRD_PARTY_FORWARD,
        discard=True,
        discard_reason="Forwarded expense belongs to a different employee",
        merchant="Uber",
        traveler_name=greet.group(1) if greet else None,
        gross_amount=amount,
        confidence=0.6,
    )


def _extract_makemytrip(text: str, subject: str) -> ExtractionResult:
    if "hotel" in subject or "voucher" in subject:
        checkin_m = re.search(r"Check-in\s*:\s*\w+,\s*(\d{1,2} \w{3} \d{4})", text)
        checkout_m = re.search(r"Check-out\s*:\s*\w+,\s*(\d{1,2} \w{3} \d{4})", text)
        nights_m = re.search(r"Nights\s*:\s*(\d+)", text)
        tariff_m = re.search(r"Tariff per night\s+INR\s+([\d,]+\.\d{2})", text)

        def _parse(m):
            return datetime.strptime(m.group(1), "%d %b %Y").date() if m else None

        return ExtractionResult(
            doc_type=ExtractedDocType.HOTEL_VOUCHER,
            discard=False,
            merchant="MakeMyTrip Hotel Voucher",
            check_in=_parse(checkin_m),
            check_out=_parse(checkout_m),
            nights=int(nights_m.group(1)) if nights_m else None,
            room_tariff_per_night=float(tariff_m.group(1).replace(",", "")) if tariff_m else None,
            confidence=0.7,
        )

    if "flight" in subject or "e-ticket" in subject:
        totals = [float(m.replace(",", "")) for m in _AMOUNT_RE.findall(text)]
        gross = sum(totals[-2:]) if len(totals) >= 2 else (totals[0] if totals else None)
        corporate = "corporate card" in text.lower()
        return ExtractionResult(
            doc_type=ExtractedDocType.FLIGHT_TICKET,
            discard=False,
            merchant="MakeMyTrip",
            gross_amount=gross,
            payment_method=PaymentMethodHint.CORPORATE_CARD if corporate else PaymentMethodHint.UNKNOWN,
            confidence=0.6,
        )

    return ExtractionResult(doc_type=ExtractedDocType.OTHER, discard=False, merchant="MakeMyTrip", confidence=0.3)
