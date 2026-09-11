"""Powers the top-of-page progress bar chart: claim counts by workflow
stage, plus personal counters for the dashboard cards.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_employee
from app.database import get_db
from app.models import ApprovalStep, Claim, Employee
from app.models.enums import ApprovalStepStatus, ClaimStatus
from app.schemas.dashboard import DashboardSummary, StageCount
from app.services import workflow

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_ALL_STAGES = [s.value for s in ClaimStatus]


@router.get("/summary", response_model=DashboardSummary)
def summary(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Claim.status, func.count(Claim.id)).group_by(Claim.status)).all())
    stage_counts = [StageCount(status=s, count=counts.get(s, 0)) for s in _ALL_STAGES]

    my_claims_count = db.scalar(select(func.count(Claim.id)).where(Claim.employee_code == employee.emp_code)) or 0

    # Every step in a claim's chain (including the terminal Finance step) is
    # inserted as PENDING up front at submission time — a step only becomes
    # actually actionable once every earlier step in the same cycle has been
    # decided. Counting raw PENDING rows here would include steps still
    # stuck behind an earlier approver, which never show up on the Approve
    # or Finance queues; only count a step if it's genuinely the *current*
    # one for its claim, exactly like /approvals/my-queue and
    # /finance/verification-queue do.
    candidate_steps = db.scalars(
        select(ApprovalStep).where(
            ApprovalStep.assigned_to_code == employee.emp_code,
            ApprovalStep.status == ApprovalStepStatus.PENDING,
        )
    ).all()
    awaiting = 0
    for step in candidate_steps:
        claim = db.get(Claim, step.claim_id)
        if claim and step.cycle_no == claim.cycle_no and workflow.current_step(claim) is step:
            awaiting += 1

    return DashboardSummary(
        my_claims_count=my_claims_count,
        awaiting_my_action_count=awaiting,
        stage_counts=stage_counts,
    )
