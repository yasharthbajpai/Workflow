"""Approve / Reject / Return-with-remarks — the "approval" half of the split
Submit/Approve experience, showing only claims currently awaiting *my*
action (policy 2.2 already resolved who that is at submit time).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_employee
from app.database import get_db
from app.models import ApprovalStep, Claim, Employee
from app.models.enums import ApprovalStepStatus, ApprovalStepType
from app.schemas.claim import ActionRequest, ClaimDetailOut, ClaimOut
from app.services import workflow
from app.services.claim_serialize import serialize_claim, serialize_claim_detail
from app.services.workflow import WorkflowError

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/my-queue", response_model=list[ClaimOut])
def my_queue(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    """Every claim where the current step (in its current cycle) is a
    BUSINESS step assigned to me and still PENDING.
    """
    pending_steps = db.scalars(
        select(ApprovalStep).where(
            ApprovalStep.assigned_to_code == employee.emp_code,
            ApprovalStep.status == ApprovalStepStatus.PENDING,
            ApprovalStep.step_type == ApprovalStepType.BUSINESS,
        )
    ).all()

    claims = []
    for step in pending_steps:
        claim = db.get(Claim, step.claim_id)
        if claim and step.cycle_no == claim.cycle_no and workflow.current_step(claim) is step:
            claims.append(claim)
    return [serialize_claim(db, c) for c in claims]


def _get_claim_for_action(db: Session, claim_id: int, employee: Employee) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    step = workflow.current_step(claim)
    if not step or step.assigned_to_code != employee.emp_code:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This claim is not awaiting your action")
    return claim


@router.post("/{claim_id}/approve", response_model=ClaimDetailOut)
def approve(claim_id: int, payload: ActionRequest, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    claim = _get_claim_for_action(db, claim_id, employee)
    try:
        claim = workflow.approve_step(db, claim, actor=employee, remarks=payload.remarks)
    except WorkflowError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return serialize_claim_detail(db, claim)


@router.post("/{claim_id}/reject", response_model=ClaimDetailOut)
def reject(claim_id: int, payload: ActionRequest, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    claim = _get_claim_for_action(db, claim_id, employee)
    try:
        claim = workflow.reject_step(db, claim, actor=employee, remarks=payload.remarks or "")
    except WorkflowError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return serialize_claim_detail(db, claim)


@router.post("/{claim_id}/return", response_model=ClaimDetailOut)
def return_claim(claim_id: int, payload: ActionRequest, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    """Policy 2.3 — return with remarks instead of approve/reject."""
    claim = _get_claim_for_action(db, claim_id, employee)
    try:
        claim = workflow.return_step(db, claim, actor=employee, remarks=payload.remarks or "")
    except WorkflowError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return serialize_claim_detail(db, claim)
