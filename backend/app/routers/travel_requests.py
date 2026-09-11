"""Travel requests + the "Scan my inbox with AI" ingestion action."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_employee, require_permission
from app.database import get_db
from app.models import Advance, Document, Employee, EstimateLine, TravelRequest
from app.models.enums import TravelRequestStatus
from app.schemas.claim import ClaimDetailOut
from app.schemas.travel import DocumentOut, TravelRequestCreate, TravelRequestOut
from app.services import policy_engine
from app.services.claim_builder import build_or_refresh_claim
from app.services.claim_serialize import serialize_claim_detail

router = APIRouter(prefix="/travel-requests", tags=["travel-requests"])


def _next_travel_request_no(db: Session) -> str:
    year = 2026
    count = db.query(TravelRequest).count()
    return f"TRQ-{year}-{count + 1:04d}"


@router.get("/mine", response_model=list[TravelRequestOut])
def my_travel_requests(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(TravelRequest)
        .options(selectinload(TravelRequest.estimate_lines))
        .where(TravelRequest.employee_code == employee.emp_code)
        .order_by(TravelRequest.id.desc())
    ).all()
    return [TravelRequestOut.model_validate(r) for r in rows]


@router.post("", response_model=TravelRequestOut, dependencies=[Depends(require_permission("travel_request.create"))])
def create_travel_request(
    payload: TravelRequestCreate,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """Creates a Travel Request from Form NTX-TRF-02: the header detail, the
    itemised estimated-cost lines, and (if one is asked for) the advance.

    The header's estimated_total is the =SUM() of the estimate lines, and the
    advance is checked against policy 1.2's ceiling on the *employee-borne*
    share of that estimate — the company-borne heads (centrally booked
    flights, hotels billed to the company) are never advanced to the
    employee, so they cannot inflate what can be drawn.
    """
    estimated_total = round(sum(line.estimate for line in payload.estimate_lines), 2)
    employee_borne = round(
        sum(line.estimate for line in payload.estimate_lines if line.borne_by == "Employee"), 2
    )

    if payload.advance_requested > 0:
        if not payload.estimate_lines:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "An advance needs an estimated-cost breakdown to be checked against — add at least one estimate line.",
            )
        max_pct = float(policy_engine.get_config(db, "ADVANCE_MAX_PCT_OF_ESTIMATE"))
        cap = round(employee_borne * max_pct / 100, 2)
        if payload.advance_requested > cap:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Advance of INR {payload.advance_requested:,.2f} exceeds policy 1.2: at most {max_pct:g}% of the "
                f"INR {employee_borne:,.2f} employee-borne estimate (INR {cap:,.2f}) can be advanced.",
            )

    header = payload.model_dump(exclude={"estimate_lines"})
    tr = TravelRequest(
        travel_request_no=_next_travel_request_no(db),
        employee_code=employee.emp_code,
        status=TravelRequestStatus.APPROVED,  # travel-approval email thread is out of scope for this build
        estimated_total=estimated_total,
        **header,
    )
    db.add(tr)
    db.flush()

    for line in payload.estimate_lines:
        db.add(EstimateLine(travel_request_id=tr.id, **line.model_dump()))

    if payload.advance_requested > 0:
        # Recorded here so the claim's settlement actually nets the advance
        # off (claim_builder reads travel_request.advance); without this row
        # an advance asked for on the form would silently never be drawn.
        db.add(
            Advance(
                travel_request_id=tr.id,
                reference=f"ADV/{tr.travel_request_no}",
                amount=payload.advance_requested,
            )
        )

    # Attach any inbox documents that were seeded for this employee but not
    # yet tied to a trip (Imran's Hyderabad pack). Without this, "Scan my
    # inbox" on a freshly created request would find zero documents.
    unlinked = db.scalars(
        select(Document).where(
            Document.employee_code == employee.emp_code,
            Document.travel_request_id.is_(None),
        )
    ).all()
    for doc in unlinked:
        doc.travel_request_id = tr.id

    db.commit()
    db.refresh(tr)
    db.refresh(tr, attribute_names=["estimate_lines"])
    return TravelRequestOut.model_validate(tr)


def _get_owned_travel_request(db: Session, travel_request_id: int, employee: Employee) -> TravelRequest:
    tr = db.get(TravelRequest, travel_request_id)
    if not tr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Travel request not found")
    if tr.employee_code != employee.emp_code:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your travel request")
    return tr


@router.get("/{travel_request_id}", response_model=TravelRequestOut)
def get_travel_request(travel_request_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    tr = _get_owned_travel_request(db, travel_request_id, employee)
    db.refresh(tr, attribute_names=["estimate_lines"])
    return TravelRequestOut.model_validate(tr)


@router.get("/{travel_request_id}/documents", response_model=list[DocumentOut])
def list_documents(travel_request_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    tr = _get_owned_travel_request(db, travel_request_id, employee)
    docs = db.scalars(select(Document).where(Document.travel_request_id == tr.id).order_by(Document.id)).all()
    return [DocumentOut.model_validate(d) for d in docs]


@router.post("/{travel_request_id}/scan", response_model=ClaimDetailOut)
def scan_inbox(
    travel_request_id: int,
    force: bool = False,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """Runs Bedrock (or the regex fallback) over every document linked to
    this travel request and (re)builds the claim's draft lines through the
    policy engine. Safe to call repeatedly — it refreshes the existing DRAFT
    claim rather than creating duplicates.

    Each document's extraction is cached after the first scan, so a plain
    re-scan re-runs only the policy engine. Pass force=true to discard those
    cached extractions and call the model again.
    """
    tr = _get_owned_travel_request(db, travel_request_id, employee)
    claim = build_or_refresh_claim(db, tr, force_reextract=force)
    return serialize_claim_detail(db, claim)
