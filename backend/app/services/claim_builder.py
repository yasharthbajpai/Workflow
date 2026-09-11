"""Orchestrates: load a travel request's documents -> extract each -> run the
policy engine -> persist a Claim (or overwrite a DRAFT claim's lines on
re-scan). This is what the "Scan my inbox with AI" button in the frontend
calls.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Advance, Claim, Document, Employee, TravelRequest
from app.models.enums import ClaimStatus
from app.services import policy_engine
from app.services.bedrock_extraction import extract_document
from app.schemas.extraction import ExtractionResult


def extract_all_documents(
    db: Session, travel_request: TravelRequest, force_reextract: bool = False
) -> list[tuple[Document, ExtractionResult]]:
    docs = db.scalars(
        select(Document).where(Document.travel_request_id == travel_request.id)
    ).all()
    # The extractor needs to know who the claimant is to tell their own
    # receipts apart from a colleague's forwarded bill (policy 4).
    claimant = db.get(Employee, travel_request.employee_code)
    results = []
    for doc in docs:
        if doc.extraction_raw_json and not force_reextract:
            ext = ExtractionResult.model_validate_json(doc.extraction_raw_json)
        else:
            ext, mode = extract_document(
                doc,
                claimant_name=claimant.name if claimant else None,
                claimant_email=claimant.email if claimant else None,
            )
            doc.extraction_mode = mode
            doc.doc_type = ext.doc_type
            doc.discarded = ext.discard
            doc.discard_reason = ext.discard_reason
            doc.extraction_raw_json = ext.model_dump_json()
        results.append((doc, ext))
    db.flush()
    return results


def build_or_refresh_claim(
    db: Session,
    travel_request: TravelRequest,
    submission_date: date | None = None,
    force_reextract: bool = False,
) -> Claim:
    """Idempotent: reuses the travel request's DRAFT claim if one exists
    (so re-scanning refreshes lines rather than creating a second claim).

    force_reextract discards each document's cached ExtractionResult and calls
    the extractor again — needed after the extraction prompt or parser changes,
    since otherwise a re-scan replays the old stored JSON.
    """
    claim = db.query(Claim).filter(
        Claim.travel_request_id == travel_request.id, Claim.status == ClaimStatus.DRAFT
    ).first()
    if claim is None:
        claim = Claim(travel_request_id=travel_request.id, employee_code=travel_request.employee_code)
        db.add(claim)
        db.flush()

    submission_date = submission_date or date.today()
    docs_and_results = extract_all_documents(db, travel_request, force_reextract=force_reextract)

    tier = policy_engine.get_city_tier(db, travel_request.city)
    draft_lines = policy_engine.build_draft_lines(db, travel_request, docs_and_results)
    policy_engine.apply_dedupe(draft_lines)
    policy_engine.apply_meal_daily_cap(db, tier, draft_lines)
    policy_engine.apply_missing_proof(draft_lines)
    policy_engine.apply_submission_window(travel_request, submission_date, draft_lines)

    policy_engine.persist_lines(db, claim, draft_lines)

    advance: Advance | None = travel_request.advance
    policy_engine.compute_claim_totals(claim, advance_amount=float(advance.amount) if advance else 0)

    db.commit()
    db.refresh(claim)
    return claim
