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

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_ALL_STAGES = [s.value for s in ClaimStatus]


@router.get("/summary", response_model=DashboardSummary)
def summary(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Claim.status, func.count(Claim.id)).group_by(Claim.status)).all())
    stage_counts = [StageCount(status=s, count=counts.get(s, 0)) for s in _ALL_STAGES]

    my_claims_count = db.scalar(select(func.count(Claim.id)).where(Claim.employee_code == employee.emp_code)) or 0

    awaiting = db.scalar(
        select(func.count(ApprovalStep.id)).where(
            ApprovalStep.assigned_to_code == employee.emp_code,
            ApprovalStep.status == ApprovalStepStatus.PENDING,
        )
    ) or 0

    return DashboardSummary(
        my_claims_count=my_claims_count,
        awaiting_my_action_count=awaiting,
        stage_counts=stage_counts,
    )
