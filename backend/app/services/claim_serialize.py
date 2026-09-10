"""Shared Claim -> ClaimOut/ClaimDetailOut serialisation, so every router
(travel_requests scan, claims detail, approvals queue, finance queue) shows
the same current-step and employee-name enrichment.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Employee
from app.schemas.claim import ApprovalStepOut, ClaimDetailOut, ClaimEventOut, ClaimLineOut, ClaimOut, PaymentOut
from app.services.workflow import current_step


def serialize_claim(db: Session, claim) -> ClaimOut:
    step = current_step(claim)
    employee = db.get(Employee, claim.employee_code)
    out = ClaimOut.model_validate(claim)
    out.employee_name = employee.name if employee else None
    out.travel_request_no = claim.travel_request.travel_request_no if claim.travel_request else None
    if step:
        out.current_step_role = step.role_code
        out.current_step_assigned_to = step.assigned_to_code
    return out


def serialize_claim_detail(db: Session, claim) -> ClaimDetailOut:
    base = serialize_claim(db, claim)
    detail = ClaimDetailOut(**base.model_dump())
    detail.lines = [ClaimLineOut.model_validate(l) for l in claim.lines]

    steps_out = []
    for s in sorted(claim.approval_steps, key=lambda s: (s.cycle_no, s.sequence)):
        assignee = db.get(Employee, s.assigned_to_code) if s.assigned_to_code else None
        step_schema = ApprovalStepOut.model_validate(s)
        step_schema.assigned_to_name = assignee.name if assignee else None
        steps_out.append(step_schema)
    detail.approval_steps = steps_out

    detail.events = [ClaimEventOut.model_validate(e) for e in claim.events]
    if claim.payment:
        detail.payment = PaymentOut.model_validate(claim.payment)
    return detail
