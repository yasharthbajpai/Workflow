"""Finance verification (policy 2.1 — required on every claim regardless of
value) + the 10th/25th payment run (policy 5.4).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_employee, require_permission
from app.database import get_db
from app.models import ApprovalStep, Claim, Employee
from app.models.enums import ApprovalStepStatus, ApprovalStepType, ClaimStatus
from app.schemas.claim import ClaimDetailOut, ClaimOut, PayRequest
from app.services import workflow
from app.services.claim_serialize import serialize_claim, serialize_claim_detail
from app.services.workflow import WorkflowError

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/verification-queue", response_model=list[ClaimOut], dependencies=[Depends(require_permission("claim.finance_verify"))])
def verification_queue(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    pending_steps = db.scalars(
        select(ApprovalStep).where(
            ApprovalStep.assigned_to_code == employee.emp_code,
            ApprovalStep.status == ApprovalStepStatus.PENDING,
            ApprovalStep.step_type == ApprovalStepType.FINANCE_VERIFICATION,
        )
    ).all()
    claims = []
    for step in pending_steps:
        claim = db.get(Claim, step.claim_id)
        if claim and step.cycle_no == claim.cycle_no and workflow.current_step(claim) is step:
            claims.append(claim)
    return [serialize_claim(db, c) for c in claims]


@router.get("/payment-run", response_model=list[ClaimOut], dependencies=[Depends(require_permission("claim.finance_verify"))])
def payment_run(db: Session = Depends(get_db)):
    rows = db.scalars(select(Claim).where(Claim.status == ClaimStatus.VERIFIED).order_by(Claim.id)).all()
    return [serialize_claim(db, c) for c in rows]


@router.post("/{claim_id}/verify", response_model=ClaimDetailOut, dependencies=[Depends(require_permission("claim.finance_verify"))])
def verify(claim_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    step = workflow.current_step(claim)
    if not step or step.assigned_to_code != employee.emp_code or step.step_type != ApprovalStepType.FINANCE_VERIFICATION:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This claim is not awaiting your Finance verification")
    try:
        claim = workflow.approve_step(db, claim, actor=employee, remarks="Verified by Finance")
    except WorkflowError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return serialize_claim_detail(db, claim)


@router.post("/{claim_id}/pay", response_model=ClaimDetailOut, dependencies=[Depends(require_permission("claim.finance_verify"))])
def pay(claim_id: int, payload: PayRequest, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    try:
        claim = workflow.release_payment(db, claim, actor=employee, reference=payload.reference)
    except WorkflowError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return serialize_claim_detail(db, claim)
