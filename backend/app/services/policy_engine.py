"""Deterministic policy engine.

Owns every rupee and every compliance verdict in the app — see the plan's
"Bedrock extracts, Python decides" design note. Nothing here reads from the
model; it only ever reads ExtractionResult objects that were already
produced (by Bedrock or the regex fallback) and turns them into ClaimLine
rows with allowed/disallowed amounts and LinePolicyFlag rows, then rolls
those up into the claim's settlement totals.

Non-obvious calls made here, each also written up in the delivery note:
  - In-room dining on a hotel folio is treated as a meal on actuals (policy 4
    bars in-room *entertainment*, not room-service food), not auto-disallowed.
  - Hotel folio tax is apportioned to the room-charge lines only, pro-rata by
    amount, since GST is charged on a subtotal that also includes
    non-reimbursable items (laundry, mini bar, in-room dining).
  - The daily meal cap, when more than one meal line falls on the same date,
    allocates the disallowed excess to the lines in the order they were
    extracted (a simplification — real folios rarely split this finely).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import CityTier, Claim, ClaimLine, Document, LinePolicyFlag, PolicyConfig, TravelRequest
from app.models.enums import ClaimSection, FlagSeverity, PaidBy
from app.schemas.extraction import ExtractedDocType, ExtractionResult, PaymentMethodHint

NON_REIMBURSABLE_KEYWORDS = [
    "laundry",
    "mini bar",
    "minibar",
    "spa",
    "gym",
    "entertainment",
    "alcohol",
    "bar charge",
    "personal call",
    "phone",
]
ROOM_KEYWORDS = ["room charge", "room tariff", "room rent"]
DINING_KEYWORDS = ["dining", "restaurant", "room service"]


def get_city_tier(db: Session, city: str | None) -> int:
    if not city:
        return 3
    row = db.get(CityTier, city.strip())
    return row.tier if row else 3


_config_cache: dict[str, str] = {}


def get_config_raw(db: Session, key: str) -> str:
    if key not in _config_cache:
        row = db.get(PolicyConfig, key)
        if not row:
            raise KeyError(f"Missing policy_config key: {key}")
        _config_cache[key] = row.value
    return _config_cache[key]


def get_config(db: Session, key: str) -> Decimal:
    return Decimal(get_config_raw(db, key))


def lodging_cap_for_tier(db: Session, tier: int) -> Decimal:
    return get_config(db, f"LODGING_CAP_TIER_{tier}")


def meal_cap_for_tier(db: Session, tier: int) -> Decimal:
    return get_config(db, "MEAL_CAP_TIER_1") if tier == 1 else get_config(db, "MEAL_CAP_TIER_2_3")


def r2(x: float | Decimal) -> float:
    return round(float(x), 2)


@dataclass
class DraftLine:
    """An unpersisted ClaimLine plus the flags to attach once it's saved."""

    section: ClaimSection
    head: str
    description: str
    gross_amount: float
    document_id: int | None
    txn_date: date | None = None
    merchant: str | None = None
    from_place: str | None = None
    to_place: str | None = None
    tax_amount: float = 0.0
    allowed_amount: float = 0.0
    disallowed_amount: float = 0.0
    disallowed_reason: str | None = None
    paid_by: PaidBy = PaidBy.EMPLOYEE
    source: str = "MANUAL"
    confidence: float | None = None
    needs_review: bool = False
    excluded: bool = False
    dedupe_key: tuple | None = None
    flags: list[tuple[str, FlagSeverity, str, str]] = field(default_factory=list)  # code, severity, ref, msg


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _hotel_invoice_key(ext: ExtractionResult) -> tuple:
    """Identity of the physical folio, independent of which document carried
    it (an .eml with the invoice as text, and a scanned/attached image of the
    same invoice both produce a HOTEL_INVOICE extraction).
    """
    if ext.bill_number:
        return ("bill_number", _norm(ext.bill_number))
    return ("composite", _norm(ext.merchant), r2(ext.subtotal or 0), r2(ext.tax_total or 0))


def _meal_or_entertainment_key(ext: ExtractionResult) -> tuple:
    amount = ext.gross_amount
    if amount is None and ext.line_items:
        amount = sum(i.amount for i in ext.line_items) + (ext.tax_total or 0)
    return (_norm(ext.merchant), r2(amount or 0))


def _duplicate_document_line(doc: Document, ext: ExtractionResult, original_doc_id: int, kind: str) -> DraftLine:
    """A second document (e.g. the same hotel invoice received as both an
    .eml body and a scanned image) describing a bill already recorded from
    another document in this claim — excluded outright, never reimbursed
    twice, mirroring the existing duplicate-cab-receipt handling.
    """
    amount = ext.gross_amount
    if amount is None and ext.line_items:
        amount = sum(i.amount for i in ext.line_items) + (ext.tax_total or 0)
    amount = amount or 0
    return DraftLine(
        section=ClaimSection.OTHER,
        head="Duplicate document",
        description=f"{ext.merchant or kind.title()} — same {kind} already recorded from document {original_doc_id}",
        gross_amount=amount,
        document_id=doc.id,
        txn_date=ext.txn_date or ext.check_in,
        merchant=ext.merchant,
        excluded=True,
        disallowed_amount=amount,
        disallowed_reason=(
            f"Duplicate {kind} — same bill already recorded from another document in this claim "
            "(likely the same document received as both text and an image) — policy 5.3"
        ),
        source=doc.extraction_mode or "MANUAL",
        confidence=ext.confidence,
        flags=[
            (
                "DUPLICATE_DOCUMENT",
                FlagSeverity.WARN,
                "5.3",
                f"Same {kind} already recorded from document {original_doc_id}",
            )
        ],
    )


def build_draft_lines(
    db: Session,
    travel_request: TravelRequest,
    documents_and_results: list[tuple[Document, ExtractionResult]],
) -> list[DraftLine]:
    """Dispatch every document's ExtractionResult into zero or more DraftLines."""
    tier = get_city_tier(db, travel_request.city)
    lines: list[DraftLine] = []
    # Tracks the *first* document that produced a given hotel-invoice or
    # meal/entertainment-bill identity, so a second document describing the
    # same physical bill (e.g. the invoice's .eml text and a scanned image
    # of the same invoice) is excluded instead of reimbursed twice.
    seen_documents: dict[tuple, int] = {}

    for doc, ext in documents_and_results:
        if ext.discard and ext.doc_type not in (
            ExtractedDocType.PAYMENT_FAILURE_NOTICE,
            ExtractedDocType.THIRD_PARTY_FORWARD,
        ):
            # Pure noise (approval threads, advance notices, promos) — never
            # a claim line at all.
            continue

        if ext.doc_type == ExtractedDocType.PAYMENT_FAILURE_NOTICE:
            lines.append(
                DraftLine(
                    section=ClaimSection.TRANSPORT,
                    head="Local conveyance",
                    description=f"{ext.merchant or 'Trip'} — payment failed, no completed transaction",
                    gross_amount=ext.gross_amount or 0,
                    document_id=doc.id,
                    txn_date=ext.txn_date,
                    merchant=ext.merchant,
                    excluded=True,
                    disallowed_amount=ext.gross_amount or 0,
                    disallowed_reason="Payment failed on this trip — no completed transaction to reimburse",
                    source=doc.extraction_mode or "MANUAL",
                    confidence=ext.confidence,
                    flags=[("PAYMENT_FAILED", FlagSeverity.INFO, "n/a", "Payment failed; no transaction occurred")],
                )
            )
            continue

        if ext.doc_type == ExtractedDocType.THIRD_PARTY_FORWARD:
            lines.append(
                DraftLine(
                    section=ClaimSection.TRANSPORT,
                    head="Local conveyance",
                    description=f"{ext.merchant or 'Trip'} — {ext.discard_reason or 'belongs to a different employee'}",
                    gross_amount=ext.gross_amount or 0,
                    document_id=doc.id,
                    txn_date=ext.txn_date,
                    merchant=ext.merchant,
                    excluded=True,
                    disallowed_amount=ext.gross_amount or 0,
                    disallowed_reason="Expense incurred by a person other than the claimant — policy 4",
                    source=doc.extraction_mode or "MANUAL",
                    confidence=ext.confidence,
                    flags=[
                        (
                            "THIRD_PARTY_EXPENSE",
                            FlagSeverity.BLOCK,
                            "4",
                            f"Receipt is addressed to {ext.traveler_name or 'another person'}, not the claimant",
                        )
                    ],
                )
            )
            continue

        if ext.doc_type == ExtractedDocType.FLIGHT_TICKET:
            lines.append(_draft_flight(doc, ext))
        elif ext.doc_type == ExtractedDocType.CAB_RECEIPT:
            lines.append(_draft_cab(doc, ext))
        elif ext.doc_type == ExtractedDocType.HOTEL_INVOICE:
            key = ("HOTEL_INVOICE", *_hotel_invoice_key(ext))
            original_doc_id = seen_documents.get(key)
            if original_doc_id is not None:
                lines.append(_duplicate_document_line(doc, ext, original_doc_id, "hotel folio"))
            else:
                seen_documents[key] = doc.id
                lines.extend(_draft_hotel_invoice(db, doc, ext, tier))
        elif ext.doc_type in (ExtractedDocType.MEAL_BILL, ExtractedDocType.BUSINESS_ENTERTAINMENT_BILL):
            key = ("MEAL_OR_BE", *_meal_or_entertainment_key(ext))
            original_doc_id = seen_documents.get(key)
            if original_doc_id is not None:
                lines.append(_duplicate_document_line(doc, ext, original_doc_id, "meal/entertainment bill"))
            else:
                seen_documents[key] = doc.id
                lines.append(_draft_meal_or_entertainment(doc, ext))
        elif ext.doc_type == ExtractedDocType.HOTEL_VOUCHER:
            # Booking intent only; the invoice (if it arrives) is the source
            # of truth for the claim, so the voucher never becomes a claim
            # line itself. NOTE: there is no reconciliation yet between the
            # voucher's booked nights/tariff and what the invoice actually
            # bills — a real mismatch (e.g. an early checkout) would go
            # unnoticed today. Flagged in the delivery note as a known gap,
            # not implemented.
            continue
        else:
            lines.append(
                DraftLine(
                    section=ClaimSection.OTHER,
                    head="Other",
                    description=doc.subject or doc.filename,
                    gross_amount=ext.gross_amount or 0,
                    document_id=doc.id,
                    txn_date=ext.txn_date,
                    merchant=ext.merchant,
                    needs_review=True,
                    source=doc.extraction_mode or "MANUAL",
                    confidence=ext.confidence,
                    flags=[("UNRECOGNISED_DOCUMENT", FlagSeverity.WARN, "n/a", "Could not classify this document confidently — please review")],
                )
            )

    return lines


def _draft_flight(doc: Document, ext: ExtractionResult) -> DraftLine:
    is_company = ext.payment_method == PaymentMethodHint.CORPORATE_CARD
    amount = ext.gross_amount or 0
    return DraftLine(
        section=ClaimSection.TRANSPORT,
        head="Air travel",
        description=f"Flight {ext.from_place or ''} - {ext.to_place or ''}".strip(" -") or (doc.subject or "Flight"),
        gross_amount=amount,
        document_id=doc.id,
        txn_date=ext.txn_date,
        merchant=ext.merchant or "Airline",
        paid_by=PaidBy.COMPANY if is_company else PaidBy.EMPLOYEE,
        allowed_amount=amount if is_company else amount,  # Company row = memo only, not reimbursed either way
        source=doc.extraction_mode or "MANUAL",
        confidence=ext.confidence,
        flags=(
            [
                (
                    "COMPANY_PAID_NOT_CLAIMABLE",
                    FlagSeverity.INFO,
                    "3.2",
                    "Booked centrally on the corporate card — recorded for audit, not reimbursed",
                )
            ]
            if is_company
            else []
        ),
    )


def _draft_cab(doc: Document, ext: ExtractionResult) -> DraftLine:
    amount = ext.gross_amount or 0
    is_company = ext.payment_method == PaymentMethodHint.CORPORATE_CARD
    flags = []
    if not doc.id:
        flags.append(("MISSING_PROOF", FlagSeverity.BLOCK, "5.2", "No supporting document reference"))
    line = DraftLine(
        section=ClaimSection.TRANSPORT,
        head="Local conveyance",
        description=f"{ext.merchant or 'Cab'}: {ext.from_place or '?'} \u2192 {ext.to_place or '?'}",
        gross_amount=amount,
        document_id=doc.id,
        txn_date=ext.txn_date,
        merchant=ext.merchant,
        from_place=ext.from_place,
        to_place=ext.to_place,
        paid_by=PaidBy.COMPANY if is_company else PaidBy.EMPLOYEE,
        source=doc.extraction_mode or "MANUAL",
        confidence=ext.confidence,
        dedupe_key=(_norm(ext.merchant), ext.txn_date, r2(amount), _norm(ext.from_place), _norm(ext.to_place)),
        flags=flags,
    )
    if not is_company:
        line.allowed_amount = amount  # policy 3.4: reimbursed on actuals against a receipt, no cap
    else:
        line.allowed_amount = amount
    return line


def _draft_meal_or_entertainment(doc: Document, ext: ExtractionResult) -> DraftLine:
    amount = ext.gross_amount
    if amount is None and ext.line_items:
        amount = sum(i.amount for i in ext.line_items) + (ext.tax_total or 0)
    amount = amount or 0

    be_threshold = None  # filled by caller via second pass (needs db); placeholder here
    is_entertainment = bool(ext.attendee_count) or ext.doc_type == ExtractedDocType.BUSINESS_ENTERTAINMENT_BILL
    head = "Business entertainment" if is_entertainment else "Meals"
    flags = []
    needs_review = False

    if is_entertainment:
        has_names = bool(ext.attendee_names) and bool(ext.attendee_org)
        if not has_names:
            flags.append(
                (
                    "BE_MISSING_ATTENDEES",
                    FlagSeverity.BLOCK,
                    "3.5",
                    "Business entertainment claim needs attendee names and organisation before it can be submitted",
                )
            )
            needs_review = True

    return DraftLine(
        section=ClaimSection.OTHER,
        head=head,
        description=f"{ext.merchant or 'Meal'}"
        + (f" — {ext.attendee_count} covers" if ext.attendee_count else ""),
        gross_amount=amount,
        document_id=doc.id,
        txn_date=ext.txn_date,
        merchant=ext.merchant,
        source=doc.extraction_mode or "MANUAL",
        confidence=ext.confidence,
        needs_review=needs_review,
        flags=flags,
    )


def _draft_hotel_invoice(db: Session, doc: Document, ext: ExtractionResult, tier: int) -> list[DraftLine]:
    lines: list[DraftLine] = []
    room_items = [i for i in ext.line_items if any(k in i.label.lower() for k in ROOM_KEYWORDS)]
    dining_items = [i for i in ext.line_items if any(k in i.label.lower() for k in DINING_KEYWORDS)]
    non_reimbursable_items = [
        i
        for i in ext.line_items
        if i not in room_items
        and i not in dining_items
        and any(k in i.label.lower() for k in NON_REIMBURSABLE_KEYWORDS)
    ]
    other_items = [i for i in ext.line_items if i not in room_items + dining_items + non_reimbursable_items]

    room_subtotal = sum(i.amount for i in room_items)
    invoice_subtotal = ext.subtotal or sum(i.amount for i in ext.line_items)
    tax_total = ext.tax_total or 0

    tax_rate = (tax_total / invoice_subtotal) if invoice_subtotal else 0
    apportioned_room_tax = r2(room_subtotal * tax_rate)

    # Prefer the model's own `nights` field over counting room_items: how
    # many room-charge lines a folio gets split into varies run-to-run (one
    # consolidated "Room Charge" line for the whole stay vs. one per night),
    # so counting them is an unstable proxy for how many nights to cap.
    nights = ext.nights or len(room_items) or 1
    per_night = room_subtotal / nights if nights else room_subtotal
    cap = float(lodging_cap_for_tier(db, tier))
    cap_total = cap * nights

    room_flags = []
    if room_subtotal > cap_total:
        disallowed = r2(room_subtotal - cap_total)
        allowed_tariff = cap_total
        room_flags.append(
            (
                "LODGING_TARIFF_EXCESS",
                FlagSeverity.WARN,
                "3.1",
                f"Room tariff INR {r2(per_night)}/night exceeds the Tier {tier} limit of INR {cap}/night; "
                f"excess of INR {disallowed} disallowed",
            )
        )
    else:
        disallowed = 0.0
        allowed_tariff = room_subtotal

    lines.append(
        DraftLine(
            section=ClaimSection.LODGING,
            head="Lodging",
            description=f"{ext.merchant or 'Hotel'} — {nights} night(s), room tariff",
            gross_amount=r2(room_subtotal + apportioned_room_tax),
            document_id=doc.id,
            txn_date=ext.check_in or ext.txn_date,
            merchant=ext.merchant,
            tax_amount=apportioned_room_tax,
            allowed_amount=r2(allowed_tariff + apportioned_room_tax),
            disallowed_amount=disallowed,
            disallowed_reason=("Tariff in excess of Tier %d limit — policy 3.1" % tier) if disallowed else None,
            source=doc.extraction_mode or "MANUAL",
            confidence=ext.confidence,
            flags=room_flags,
        )
    )

    for item in non_reimbursable_items:
        lines.append(
            DraftLine(
                section=ClaimSection.OTHER,
                head="Hotel — non-reimbursable",
                description=f"{ext.merchant or 'Hotel'} — {item.label}",
                gross_amount=item.amount,
                document_id=doc.id,
                txn_date=item.item_date or ext.txn_date,
                merchant=ext.merchant,
                allowed_amount=0,
                disallowed_amount=item.amount,
                disallowed_reason=f"{item.label} is never reimbursed — policy 4",
                source=doc.extraction_mode or "MANUAL",
                confidence=ext.confidence,
                flags=[("NON_REIMBURSABLE_ITEM", FlagSeverity.WARN, "4", f"{item.label} excluded per policy 4")],
            )
        )

    for item in dining_items:
        lines.append(
            DraftLine(
                section=ClaimSection.OTHER,
                head="Meals",
                description=f"{ext.merchant or 'Hotel'} — {item.label} (in-room dining, treated as a meal)",
                gross_amount=item.amount,
                document_id=doc.id,
                txn_date=item.item_date or ext.txn_date,
                merchant=ext.merchant,
                allowed_amount=item.amount,  # capped in the meal-cap pass below
                source=doc.extraction_mode or "MANUAL",
                confidence=ext.confidence,
                needs_review=True,
                flags=[
                    (
                        "IN_ROOM_DINING_AS_MEAL",
                        FlagSeverity.INFO,
                        "4",
                        "In-room dining treated as a meal claim (not in-room entertainment) — assumption, see delivery note",
                    )
                ],
            )
        )

    for item in other_items:
        lines.append(
            DraftLine(
                section=ClaimSection.OTHER,
                head="Hotel — other",
                description=f"{ext.merchant or 'Hotel'} — {item.label}",
                gross_amount=item.amount,
                document_id=doc.id,
                txn_date=item.item_date or ext.txn_date,
                merchant=ext.merchant,
                needs_review=True,
                source=doc.extraction_mode or "MANUAL",
                confidence=ext.confidence,
                flags=[("UNRECOGNISED_HOTEL_LINE", FlagSeverity.WARN, "n/a", "Could not classify this folio line — please review")],
            )
        )

    return lines


def apply_meal_daily_cap(db: Session, tier: int, draft_lines: list[DraftLine]) -> None:
    """Second pass: cap Meals-head lines per day per policy 3.3."""
    cap = float(meal_cap_for_tier(db, tier))
    by_day: dict[date, list[DraftLine]] = defaultdict(list)
    for line in draft_lines:
        if line.head == "Meals" and not line.excluded and line.txn_date:
            by_day[line.txn_date].append(line)

    for day, day_lines in by_day.items():
        total = sum(l.allowed_amount for l in day_lines)
        if total <= cap:
            continue
        excess = r2(total - cap)
        for line in day_lines:
            take = min(excess, line.allowed_amount)
            if take <= 0:
                continue
            line.allowed_amount = r2(line.allowed_amount - take)
            line.disallowed_amount = r2(line.disallowed_amount + take)
            line.disallowed_reason = f"Meal claims exceed the Tier {tier} daily cap of INR {cap} — policy 3.3"
            line.flags.append(
                (
                    "MEAL_CAP_EXCEEDED",
                    FlagSeverity.WARN,
                    "3.3",
                    f"Daily meal total INR {total} exceeds the INR {cap} cap; INR {take} disallowed on this line",
                )
            )
            excess = r2(excess - take)
            if excess <= 0:
                break


def apply_dedupe(draft_lines: list[DraftLine]) -> None:
    """Policy 5.3 — duplicate submission of the same bill. First occurrence
    wins; later ones are excluded and point back at the original.
    """
    seen: dict[tuple, DraftLine] = {}
    for line in draft_lines:
        if line.excluded or not line.dedupe_key or line.gross_amount == 0:
            continue
        original = seen.get(line.dedupe_key)
        if original is None:
            seen[line.dedupe_key] = line
            continue
        line.excluded = True
        line.disallowed_amount = line.gross_amount
        line.allowed_amount = 0
        line.disallowed_reason = "Duplicate of another line in this claim — policy 5.3"
        line.flags.append(
            (
                "DUPLICATE_BILL",
                FlagSeverity.WARN,
                "5.3",
                f"Same merchant/date/amount/route as another line already in this claim",
            )
        )


def apply_missing_proof(draft_lines: list[DraftLine]) -> None:
    for line in draft_lines:
        if line.excluded:
            continue
        if not line.document_id:
            line.flags.append(("MISSING_PROOF", FlagSeverity.BLOCK, "5.2", "No supporting document reference"))
            line.needs_review = True


def apply_submission_window(travel_request: TravelRequest, submission_date: date, draft_lines: list[DraftLine]) -> None:
    days_since_return = (submission_date - travel_request.to_date).days
    if days_since_return > 7:
        for line in draft_lines:
            line.flags.append(
                (
                    "LATE_SUBMISSION",
                    FlagSeverity.WARN,
                    "5.1",
                    f"Submitted {days_since_return} days after return; policy 5.1 requires submission within 7 calendar days",
                )
            )


def persist_lines(db: Session, claim: Claim, draft_lines: list[DraftLine]) -> None:
    claim.lines.clear()
    persisted: dict[int, ClaimLine] = {}
    for idx, d in enumerate(draft_lines):
        cl = ClaimLine(
            section=d.section,
            head=d.head,
            txn_date=d.txn_date,
            description=d.description,
            merchant=d.merchant,
            from_place=d.from_place,
            to_place=d.to_place,
            gross_amount=d.gross_amount,
            tax_amount=d.tax_amount,
            allowed_amount=d.allowed_amount,
            disallowed_amount=d.disallowed_amount,
            disallowed_reason=d.disallowed_reason,
            paid_by=d.paid_by,
            proof_document_id=d.document_id,
            proof_ref=f"doc:{d.document_id}" if d.document_id else None,
            source=d.source,
            confidence=d.confidence,
            needs_review=d.needs_review,
            excluded=d.excluded,
        )
        for code, severity, ref, msg in d.flags:
            cl.flags.append(LinePolicyFlag(code=code, severity=severity, policy_ref=ref, message=msg))
        claim.lines.append(cl)
        persisted[idx] = cl
    db.flush()


def compute_claim_totals(claim: Claim, advance_amount: float = 0) -> None:
    # Numeric columns come back as Decimal; normalise everything to float
    # up front so this never trips a Decimal/float TypeError.
    employee_paid = sum(float(l.allowed_amount) for l in claim.lines if l.paid_by == PaidBy.EMPLOYEE and not l.excluded)
    company_paid = sum(float(l.allowed_amount) for l in claim.lines if l.paid_by == PaidBy.COMPANY and not l.excluded)
    disallowed = sum(float(l.disallowed_amount) for l in claim.lines)
    advance_amount = float(advance_amount)

    net = employee_paid  # only Employee-paid rows are ever reimbursed (legend B64)
    payable = max(r2(net - advance_amount), 0)
    recoverable = max(r2(advance_amount - net), 0)

    claim.total_employee_paid = r2(employee_paid)
    claim.total_company_paid = r2(company_paid)
    claim.total_disallowed = r2(disallowed)
    claim.net_reimbursable = r2(net)
    claim.advance_drawn = r2(advance_amount)
    claim.amount_payable = payable
    claim.amount_recoverable = recoverable


def has_blocking_flags(claim: Claim) -> list[LinePolicyFlag]:
    blocking = []
    for line in claim.lines:
        if line.excluded:
            continue
        for flag in line.flags:
            if flag.severity == FlagSeverity.BLOCK:
                blocking.append(flag)
    return blocking
