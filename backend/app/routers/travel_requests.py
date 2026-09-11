"""Travel requests + the "Scan my inbox with AI" ingestion action."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_employee, require_permission
from app.database import get_db
from app.models import Document, Employee, TravelRequest
from app.models.enums import TravelRequestStatus
from app.schemas.claim import ClaimDetailOut
from app.schemas.travel import DocumentOut, TravelRequestCreate, TravelRequestOut
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
        select(TravelRequest).where(TravelRequest.employee_code == employee.emp_code).order_by(TravelRequest.id.desc())
    ).all()
    return [TravelRequestOut.model_validate(r) for r in rows]


@router.post("", response_model=TravelRequestOut, dependencies=[Depends(require_permission("travel_request.create"))])
def create_travel_request(
    payload: TravelRequestCreate,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    tr = TravelRequest(
        travel_request_no=_next_travel_request_no(db),
        employee_code=employee.emp_code,
        status=TravelRequestStatus.APPROVED,  # travel-approval email thread is out of scope for this build
        **payload.model_dump(),
    )
    db.add(tr)
    db.commit()
    db.refresh(tr)
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
    return TravelRequestOut.model_validate(tr)


@router.get("/{travel_request_id}/documents", response_model=list[DocumentOut])
def list_documents(travel_request_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    tr = _get_owned_travel_request(db, travel_request_id, employee)
    docs = db.scalars(select(Document).where(Document.travel_request_id == tr.id).order_by(Document.id)).all()
    return [DocumentOut.model_validate(d) for d in docs]


@router.post("/{travel_request_id}/scan", response_model=ClaimDetailOut)
def scan_inbox(travel_request_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    """Runs Bedrock (or the regex fallback) over every document linked to
    this travel request and (re)builds the claim's draft lines through the
    policy engine. Safe to call repeatedly — it refreshes the existing DRAFT
    claim rather than creating duplicates.
    """
    tr = _get_owned_travel_request(db, travel_request_id, employee)
    claim = build_or_refresh_claim(db, tr)
    return serialize_claim_detail(db, claim)
