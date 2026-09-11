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

_SYSTEM_PROMPT_TEMPLATE = """You are an expense-document parser for an Indian company's travel desk.
You will be shown the text (or image) of ONE email or receipt from an employee's inbox.

The inbox belongs to {owner_name} ({owner_email}). They are the claimant: the only
person whose expenses may be claimed from this inbox.

Extract it into the given JSON schema exactly, by calling the extract_expense_document tool. Rules:
- If the message is a travel-approval thread, an advance-disbursement notice, a marketing/promo
  email, or otherwise not a specific claimable transaction, set discard=true with a short reason.
- If a payment failed (e.g. "Payment failed", "We could not charge your card"), set
  doc_type=PAYMENT_FAILURE_NOTICE and discard=true — it is not a valid expense.
- Always set traveler_name to whoever the receipt greets or was booked for, when shown.
- A first-name-only greeting that matches {owner_name}'s own first name IS the claimant.
  "Thanks for riding, {owner_first_name}" is {owner_name}'s own receipt — classify it as the
  normal document type (e.g. CAB_RECEIPT), never THIRD_PARTY_FORWARD.
- Only use doc_type=THIRD_PARTY_FORWARD when the expense genuinely belongs to a DIFFERENT
  person than {owner_name} — e.g. "Thanks for riding, Deepa", or a colleague forwarding their
  own bill and asking for it to be added to the claim.
- Being a forward is NOT by itself third-party. {owner_name} re-sending or forwarding their own
  receipt is still their own expense: classify it by what the receipt actually is. Duplicates are
  detected later by a separate step, so do not discard a document merely for looking repeated.
- If one ticket or invoice covers MULTIPLE sectors/segments/nights (e.g. an outbound flight and a
  return flight on the same booking), emit one entry in line_items per sector with its own amount
  and date, and set gross_amount to the total across all of them.
- For itemised bills (hotel folios, restaurant bills) populate line_items with every line,
  plus subtotal and tax_total exactly as printed. Do not compute or apportion anything yourself.
- For business entertainment / hosted meals, extract attendee_count and any attendee names or
  organisation mentioned, even if incomplete.
- If the document is only a covering note referring to an attachment ("bill attached") and shows
  no amount itself, set discard=true with reason "covering note, amount is in the attachment" —
  the attachment is parsed separately and is the source of truth.
- Never invent numbers or dates. If a field is not present in the document, leave it null/empty.
  In particular do not guess a year: use the year printed on the document or in its Date header.
"""


def _system_prompt(claimant_name: str | None, claimant_email: str | None) -> str:
    name = claimant_name or "the employee"
    return _SYSTEM_PROMPT_TEMPLATE.format(
        owner_name=name,
        owner_email=claimant_email or "unknown",
        owner_first_name=name.split()[0],
    )


def _first_name(full_name: str | None) -> str:
    return (full_name or "").strip().split()[0].lower() if (full_name or "").strip() else ""


def _greeting_is_claimant(greeting_name: str | None, claimant_name: str | None) -> bool:
    """A receipt greeting like "Chaitanya" belongs to the claimant when it
    matches any part of their name. Used by the regex fallback, which has no
    model to reason about identity for it.
    """
    if not greeting_name:
        return False
    if not claimant_name:
        return True  # unknown claimant: assume the inbox owner's own receipt
    greeting = greeting_name.strip().lower()
    parts = [p.lower() for p in claimant_name.split()]
    return greeting in parts or greeting == claimant_name.strip().lower()

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


def extract_document(
    document: Document,
    claimant_name: str | None = None,
    claimant_email: str | None = None,
) -> tuple[ExtractionResult, ExtractionMode]:
    """Extract one document. The claimant's identity is required to tell the
    claimant's own receipts apart from a colleague's forwarded expense — both
    the model prompt and the regex fallback need it, so it is threaded in
    rather than inferred from the document alone.
    """
    if settings.bedrock_model_id:
        try:
            result = _extract_with_bedrock(document, claimant_name, claimant_email)
            return result, ExtractionMode.BEDROCK
        except Exception:  # noqa: BLE001 — any SDK/network/credentials failure falls back
            logger.exception("Bedrock extraction failed for document %s, falling back to regex", document.id)
    result = _extract_with_regex(document, claimant_name)
    return result, ExtractionMode.REGEX_FALLBACK


def _image_format(mime_type: str | None) -> str:
    fmt = (mime_type or "image/png").split("/")[-1].lower()
    return "jpeg" if fmt == "jpg" else fmt


def _extract_with_bedrock(
    document: Document,
    claimant_name: str | None = None,
    claimant_email: str | None = None,
) -> ExtractionResult:
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
        system=[{"text": _system_prompt(claimant_name, claimant_email)}],
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


def _extract_with_regex(document: Document, claimant_name: str | None = None) -> ExtractionResult:
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
        return _extract_uber(text, claimant_name)
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
        # A forward is only third-party when the receipt greets someone other
        # than the claimant; the claimant re-sending their own receipt is still
        # their own expense (the dedupe pass catches the repeat).
        return _extract_uber(text, claimant_name)

    return ExtractionResult(doc_type=ExtractedDocType.OTHER, discard=False, confidence=0.2)


def _extract_uber(text: str, claimant_name: str | None = None) -> ExtractionResult:
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

    greeting_name = greet.group(1) if greet else None
    if greeting_name and not _greeting_is_claimant(greeting_name, claimant_name):
        return _extract_third_party_forward(text, greeting_name, claimant_name)

    return ExtractionResult(
        doc_type=ExtractedDocType.CAB_RECEIPT,
        discard=False,
        merchant="Uber",
        traveler_name=greeting_name,
        txn_date=txn_date,
        from_place=pickup.group(1).strip() if pickup else None,
        to_place=drop.group(1).strip() if drop else None,
        gross_amount=amount,
        payment_method=PaymentMethodHint.PERSONAL_CARD if "personal" in text.lower() else PaymentMethodHint.UNKNOWN,
        confidence=0.75,
    )


def _extract_third_party_forward(
    text: str,
    greeting_name: str | None = None,
    claimant_name: str | None = None,
) -> ExtractionResult:
    amount = _to_amount(text)
    if greeting_name is None:
        greet = re.search(r"riding,\s*(\w+)", text)
        greeting_name = greet.group(1) if greet else None
    who = greeting_name or "another employee"
    return ExtractionResult(
        doc_type=ExtractedDocType.THIRD_PARTY_FORWARD,
        discard=True,
        discard_reason=(
            f"Receipt is addressed to {who}, not the claimant"
            + (f" ({claimant_name})" if claimant_name else "")
        ),
        merchant="Uber",
        traveler_name=greeting_name,
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
