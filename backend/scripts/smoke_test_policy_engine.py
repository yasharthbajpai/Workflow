"""Manual verification script (not pytest) for the policy engine.

Builds the ExtractionResult that Bedrock is expected to produce for every
seeded document in Chaitanya Reddy's Bengaluru trip, feeds them through the
policy engine exactly the way /travel-requests/{id}/scan does, and asserts
the numbers the plan calls out explicitly:
  - the three INR 172 Uber receipts collapse to one (payment-failure notice
    discarded outright, the resend deduped against the original)
  - Deepa's forwarded INR 640 Chennai cab is excluded as a third-party expense
  - both flight sectors are Company-paid memo rows, never reimbursed
  - the hotel folio's GST is apportioned onto the room tariff only
    (INR 17,250 x 12% = INR 2,070, not the full INR 2,304 on the invoice)
  - the INR 2,255 dinner is blocked as business entertainment missing
    attendee names

Run with: backend/.venv/bin/python -m scripts.smoke_test_policy_engine
"""
from datetime import date

from app.database import SessionLocal
from app.models import Document, TravelRequest
from app.models.enums import ExtractionMode
from app.schemas.extraction import ExtractedDocType, ExtractedLineItem, ExtractionResult, PaymentMethodHint
from app.services import policy_engine
from app.services.claim_builder import build_or_refresh_claim

# doc filename -> the ExtractionResult Bedrock is expected to return for it.
EXPECTED: dict[str, ExtractionResult] = {
    "01_travel_approval_request.eml": ExtractionResult(doc_type=ExtractedDocType.TRAVEL_APPROVAL_REQUEST, discard=True),
    "02_travel_approval_granted.eml": ExtractionResult(doc_type=ExtractedDocType.TRAVEL_APPROVAL_GRANTED, discard=True),
    "03_advance_disbursed.eml": ExtractionResult(doc_type=ExtractedDocType.ADVANCE_NOTICE, discard=True),
    "04_flight_eticket.eml": ExtractionResult(
        doc_type=ExtractedDocType.FLIGHT_TICKET,
        discard=False,
        merchant="IndiGo / MakeMyTrip",
        gross_amount=5016.00 + 5540.00,
        payment_method=PaymentMethodHint.CORPORATE_CARD,
        from_place="Pune",
        to_place="Bengaluru",
    ),
    "05_hotel_voucher.eml": ExtractionResult(
        doc_type=ExtractedDocType.HOTEL_VOUCHER,
        discard=False,
        merchant="Keys Prime Hotel, Whitefield",
        check_in=date(2026, 6, 16),
        check_out=date(2026, 6, 19),
        nights=3,
        room_tariff_per_night=5750.00,
    ),
    "06_uber_receipt_1.eml": ExtractionResult(
        doc_type=ExtractedDocType.CAB_RECEIPT,
        discard=False,
        merchant="Uber",
        traveler_name="Chaitanya",
        txn_date=date(2026, 6, 16),
        from_place="Baner, Pune",
        to_place="Pune International Airport (PNQ)",
        gross_amount=1415.02,
        payment_method=PaymentMethodHint.PERSONAL_CARD,
    ),
    "07_uber_receipt_2.eml": ExtractionResult(
        doc_type=ExtractedDocType.CAB_RECEIPT,
        discard=False,
        merchant="Uber",
        traveler_name="Chaitanya",
        txn_date=date(2026, 6, 16),
        from_place="Kempegowda International Airport (BLR)",
        to_place="Keys Prime Hotel, Whitefield",
        gross_amount=743.00,
        payment_method=PaymentMethodHint.PERSONAL_CARD,
    ),
    "08_uber_payment_failed.eml": ExtractionResult(
        doc_type=ExtractedDocType.PAYMENT_FAILURE_NOTICE,
        discard=True,
        gross_amount=172.00,
    ),
    "09_uber_receipt_3.eml": ExtractionResult(
        doc_type=ExtractedDocType.CAB_RECEIPT,
        discard=False,
        merchant="Uber",
        traveler_name="Chaitanya",
        txn_date=date(2026, 6, 17),
        from_place="Vertex Technologies, Whitefield",
        to_place="Keys Prime Hotel, Whitefield",
        gross_amount=172.00,
        payment_method=PaymentMethodHint.PERSONAL_CARD,
    ),
    "10_uber_receipt_3_resend.eml": ExtractionResult(
        doc_type=ExtractedDocType.CAB_RECEIPT,
        discard=False,
        merchant="Uber",
        traveler_name="Chaitanya",
        txn_date=date(2026, 6, 17),
        from_place="Vertex Technologies, Whitefield",
        to_place="Keys Prime Hotel, Whitefield",
        gross_amount=172.00,
        payment_method=PaymentMethodHint.PERSONAL_CARD,
    ),
    "11_dinner_bill.eml": ExtractionResult(
        doc_type=ExtractedDocType.BUSINESS_ENTERTAINMENT_BILL,
        discard=False,
        merchant="Spice Terrace",
        txn_date=date(2026, 6, 18),
        gross_amount=2255.00,
        attendee_count=4,
        attendee_names=[],
        attendee_org=None,
    ),
    "12_hotel_invoice.eml": ExtractionResult(
        doc_type=ExtractedDocType.HOTEL_INVOICE,
        discard=False,
        merchant="Keys Prime Whitefield",
        bill_number="KPW/26-27/1188",
        check_in=date(2026, 6, 16),
        check_out=date(2026, 6, 19),
        nights=3,
        line_items=[
            ExtractedLineItem(label="Room Charge", item_date=date(2026, 6, 16), amount=5750.00),
            ExtractedLineItem(label="Room Charge", item_date=date(2026, 6, 17), amount=5750.00),
            ExtractedLineItem(label="Laundry", item_date=date(2026, 6, 17), amount=450.00),
            ExtractedLineItem(label="Room Charge", item_date=date(2026, 6, 18), amount=5750.00),
            ExtractedLineItem(label="Mini Bar", item_date=date(2026, 6, 18), amount=380.00),
            ExtractedLineItem(label="In Room Dining", item_date=date(2026, 6, 18), amount=1120.00),
        ],
        subtotal=19200.00,
        tax_total=2304.00,
    ),
    "13_colleague_forward.eml": ExtractionResult(
        doc_type=ExtractedDocType.THIRD_PARTY_FORWARD,
        discard=True,
        discard_reason="Forwarded expense belongs to Deepa Nair, a different employee",
        merchant="Uber",
        traveler_name="Deepa",
        gross_amount=640.00,
    ),
    "14_promo_noise.eml": ExtractionResult(doc_type=ExtractedDocType.PROMOTIONAL_NOISE, discard=True),
    "15_return_cab.eml": ExtractionResult(
        doc_type=ExtractedDocType.CAB_RECEIPT,
        discard=False,
        merchant="Uber",
        traveler_name="Chaitanya",
        txn_date=date(2026, 6, 20),
        from_place="Pune International Airport (PNQ)",
        to_place="Baner, Pune",
        gross_amount=1229.02,
        payment_method=PaymentMethodHint.PERSONAL_CARD,
    ),
    "hotel_invoice_1188.png": ExtractionResult(doc_type=ExtractedDocType.OTHER, discard=True, discard_reason="duplicate image of the invoice email"),
    "dinner_bill_18jun.png": ExtractionResult(doc_type=ExtractedDocType.OTHER, discard=True, discard_reason="duplicate image of the dinner bill email"),
}


def main() -> None:
    db = SessionLocal()
    tr = db.query(TravelRequest).filter(TravelRequest.travel_request_no == "TRQ-2026-0001").one()

    docs = db.query(Document).filter(Document.travel_request_id == tr.id).all()
    for doc in docs:
        ext = EXPECTED[doc.filename]
        doc.extraction_mode = ExtractionMode.MANUAL
        doc.doc_type = ext.doc_type
        doc.discarded = ext.discard
        doc.extraction_raw_json = ext.model_dump_json()
    db.commit()

    claim = build_or_refresh_claim(db, tr, submission_date=date(2026, 6, 22))

    print(f"\nClaim #{claim.id} — {len(claim.lines)} lines\n" + "=" * 70)
    for l in claim.lines:
        tag = "EXCLUDED" if l.excluded else ("REVIEW" if l.needs_review else "OK")
        print(
            f"[{tag:8}] {l.section:10} {l.head:24} gross={l.gross_amount:>9} "
            f"allow={l.allowed_amount:>9} disallow={l.disallowed_amount:>9} paid_by={l.paid_by}"
        )
        for f in l.flags:
            print(f"            - {f.severity} {f.code} (policy {f.policy_ref}): {f.message}")

    print("\nTotals" + "=" * 64)
    print(f"  total_employee_paid = {claim.total_employee_paid}")
    print(f"  total_company_paid  = {claim.total_company_paid}")
    print(f"  total_disallowed    = {claim.total_disallowed}")
    print(f"  net_reimbursable    = {claim.net_reimbursable}")
    print(f"  advance_drawn       = {claim.advance_drawn}")
    print(f"  amount_payable      = {claim.amount_payable}")
    print(f"  amount_recoverable  = {claim.amount_recoverable}")

    # --- Assertions -----------------------------------------------------
    non_excluded = [l for l in claim.lines if not l.excluded]
    uber_172_all = [l for l in claim.lines if l.gross_amount == 172.00]
    uber_172_live = [l for l in uber_172_all if not l.excluded]
    assert len(uber_172_all) == 3, f"expected payment-failure notice + real receipt + resend, got {len(uber_172_all)}"
    assert len(uber_172_live) == 1, f"expected only the real receipt to remain unexcluded, got {len(uber_172_live)}"

    third_party = [l for l in claim.lines if l.gross_amount == 640.00]
    assert len(third_party) == 1 and third_party[0].excluded, "Deepa's cab must be excluded"

    flight_lines = [l for l in claim.lines if l.head == "Air travel"]
    assert flight_lines and all(l.paid_by == "Company" for l in flight_lines), "flights must be Company-paid"

    lodging_lines = [l for l in claim.lines if l.head == "Lodging"]
    assert len(lodging_lines) == 1
    assert lodging_lines[0].tax_amount == 2070.00, f"expected apportioned tax 2070.00, got {lodging_lines[0].tax_amount}"
    assert lodging_lines[0].disallowed_amount == 0, "tariff is within the Tier 1 cap, nothing should be disallowed"

    laundry = [l for l in claim.lines if "Laundry" in l.description]
    assert laundry and laundry[0].disallowed_amount == 450.00
    minibar = [l for l in claim.lines if "Mini Bar" in l.description]
    assert minibar and minibar[0].disallowed_amount == 380.00

    dinner = [l for l in claim.lines if l.head == "Business entertainment"]
    assert dinner and any(f.code == "BE_MISSING_ATTENDEES" for f in dinner[0].flags), "dinner must be blocked for missing attendees"

    blocking = policy_engine.has_blocking_flags(claim)
    assert blocking, "claim should have at least one BLOCK flag (missing BE attendees) preventing submission"

    print("\nAll assertions passed.")
    db.close()


if __name__ == "__main__":
    main()
