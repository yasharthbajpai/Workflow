from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_employee
from app.database import get_db
from app.models import Claim, ClaimLine, Employee
from app.models.enums import ClaimStatus, FlagSeverity
from app.schemas.claim import ClaimDetailOut, ClaimLinePatch, ClaimOut
from app.services import policy_engine, workflow
from app.services.claim_serialize import serialize_claim, serialize_claim_detail
from app.services.workflow import WorkflowError

router = APIRouter(prefix="/claims", tags=["claims"])


def _can_view(claim: Claim, employee: Employee) -> bool:
    if claim.employee_code == employee.emp_code:
        return True
    if employee.role_code in ("REPORTING_MANAGER", "HOD", "HOD_DIVISION", "MD", "FINANCE"):
        return True  # simplification: any approver-capable role can view for audit purposes
    return False


def _get_visible_claim(db: Session, claim_id: int, employee: Employee) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if not _can_view(claim, employee):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to view this claim")
    return claim


@router.get("/mine", response_model=list[ClaimOut])
def my_claims(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Claim).where(Claim.employee_code == employee.emp_code).order_by(Claim.id.desc())
    ).all()
    return [serialize_claim(db, c) for c in rows]


@router.get("/{claim_id}", response_model=ClaimDetailOut)
def get_claim(claim_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    claim = _get_visible_claim(db, claim_id, employee)
    return serialize_claim_detail(db, claim)


@router.patch("/{claim_id}/lines/{line_id}", response_model=ClaimDetailOut)
def patch_line(
    claim_id: int,
    line_id: int,
    payload: ClaimLinePatch,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """Lets the employee correct a line before (re)submitting — most
    commonly, supplying the attendee names/organisation a business
    entertainment claim was missing so the BE_MISSING_ATTENDEES BLOCK flag
    can clear (policy 3.5).
    """
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if claim.employee_code != employee.emp_code:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your claim")
    if claim.status not in (ClaimStatus.DRAFT, ClaimStatus.RETURNED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot edit a claim in status {claim.status}")

    line = db.get(ClaimLine, line_id)
    if not line or line.claim_id != claim.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim line not found")

    if payload.description is not None:
        line.description = payload.description
    if payload.attendee_names is not None or payload.attendee_org is not None:
        extra = json.loads(line.extra_json) if line.extra_json else {}
        if payload.attendee_names is not None:
            extra["attendee_names"] = payload.attendee_names
        if payload.attendee_org is not None:
            extra["attendee_org"] = payload.attendee_org
        line.extra_json = json.dumps(extra)
        # Business entertainment now properly documented -> it becomes
        # reimbursable on actuals (still subject to any other flags).
        if payload.attendee_names and payload.attendee_org:
            line.allowed_amount = line.gross_amount - line.disallowed_amount
    if payload.gross_amount is not None:
        line.gross_amount = payload.gross_amount
    if payload.allowed_amount is not None:
        line.allowed_amount = payload.allowed_amount
    if payload.disallowed_amount is not None:
        line.disallowed_amount = payload.disallowed_amount
    if payload.disallowed_reason is not None:
        line.disallowed_reason = payload.disallowed_reason
    if payload.paid_by is not None:
        line.paid_by = payload.paid_by

    if payload.clear_flag_codes:
        line.flags = [f for f in line.flags if f.code not in payload.clear_flag_codes]
        if not any(f.severity == FlagSeverity.BLOCK for f in line.flags):
            line.needs_review = False

    db.flush()
    advance_amount = float(claim.travel_request.advance.amount) if claim.travel_request.advance else 0
    policy_engine.compute_claim_totals(claim, advance_amount=advance_amount)
    db.commit()
    db.refresh(claim)
    return serialize_claim_detail(db, claim)


@router.post("/{claim_id}/submit", response_model=ClaimDetailOut)
def submit(claim_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if claim.employee_code != employee.emp_code:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your claim")
    try:
        claim = workflow.submit_claim(db, claim, claim.travel_request, employee, actor=employee)
    except WorkflowError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return serialize_claim_detail(db, claim)


@router.post("/{claim_id}/resubmit", response_model=ClaimDetailOut)
def resubmit(claim_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if claim.employee_code != employee.emp_code:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your claim")
    try:
        claim = workflow.resubmit_claim(db, claim, claim.travel_request, employee, actor=employee)
    except WorkflowError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return serialize_claim_detail(db, claim)
