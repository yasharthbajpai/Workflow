"""Claim state machine: submit, approve/reject/return, finance verify, pay.

Ties together app/services/policy_engine.py (money + BLOCK flags) and
app/services/routing.py (who has to sign off, per policy 2.1/2.2) and
implements policy 2.3 (return-with-remarks + same-TRQ resubmission).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import ApprovalStep, Claim, ClaimEvent, Employee, Payment, TravelRequest
from app.models.enums import ApprovalStepStatus, ApprovalStepType, ClaimStatus, PaymentStatus
from app.services import policy_engine, routing


class WorkflowError(Exception):
    """Raised for any invalid state transition; routers turn this into HTTP 400."""


def _log_event(db: Session, claim: Claim, actor: Employee | None, event_type: str, detail: str | None = None) -> None:
    db.add(ClaimEvent(claim_id=claim.id, actor_code=actor.emp_code if actor else None, event_type=event_type, detail=detail))


def _cancel_remaining_steps(claim: Claim, decided_step: ApprovalStep, reason: str) -> None:
    """After a REJECT or RETURN, every later step in the same cycle that was
    still PENDING is moot — mark it SKIPPED so it never lingers as a phantom
    entry in someone else's approval queue.
    """
    for s in claim.approval_steps:
        if s.cycle_no == claim.cycle_no and s.sequence > decided_step.sequence and s.status == ApprovalStepStatus.PENDING:
            s.status = ApprovalStepStatus.SKIPPED
            s.skip_reason = reason


def build_approval_steps(db: Session, claim: Claim, travel_request: TravelRequest, claimant: Employee) -> None:
    """Creates every ApprovalStep for the claim's *current* cycle_no: the
    value-banded business levels (policy 2, routed per 2.2), then Finance
    unconditionally as the terminal step (policy 2.1).
    """
    band = routing.select_approval_band(db, float(claim.total_employee_paid), travel_request.is_international)
    resolved_chain = routing.resolve_approval_chain(db, claimant, band.required_levels)

    sequence = 1
    for step in resolved_chain:
        if step.assigned_to is None:
            status = ApprovalStepStatus.SKIPPED
        else:
            status = ApprovalStepStatus.PENDING
        db.add(
            ApprovalStep(
                claim_id=claim.id,
                cycle_no=claim.cycle_no,
                sequence=sequence,
                step_type=ApprovalStepType.BUSINESS,
                role_code=step.role_code,
                assigned_to_code=step.assigned_to.emp_code if step.assigned_to else None,
                status=status,
                skip_reason=step.skip_reason,
            )
        )
        sequence += 1

    finance = routing.finance_verifier(db)
    db.add(
        ApprovalStep(
            claim_id=claim.id,
            cycle_no=claim.cycle_no,
            sequence=sequence,
            step_type=ApprovalStepType.FINANCE_VERIFICATION,
            role_code="FINANCE",
            assigned_to_code=finance.emp_code,
            status=ApprovalStepStatus.PENDING,
        )
    )
    db.flush()


def current_step(claim: Claim) -> ApprovalStep | None:
    """The next step awaiting action in the claim's current cycle, or None
    if every step in this cycle is already decided.
    """
    steps = [s for s in claim.approval_steps if s.cycle_no == claim.cycle_no]
    steps.sort(key=lambda s: s.sequence)
    for step in steps:
        if step.status == ApprovalStepStatus.PENDING:
            return step
    return None


def submit_claim(db: Session, claim: Claim, travel_request: TravelRequest, claimant: Employee, actor: Employee) -> Claim:
    if claim.status not in (ClaimStatus.DRAFT,):
        raise WorkflowError(f"Cannot submit a claim in status {claim.status}")

    blocking = policy_engine.has_blocking_flags(claim)
    if blocking:
        codes = ", ".join(sorted({f.code for f in blocking}))
        raise WorkflowError(f"Claim has unresolved blocking issues: {codes}")

    build_approval_steps(db, claim, travel_request, claimant)
    claim.status = ClaimStatus.PENDING_APPROVAL
    claim.submitted_at = datetime.now(timezone.utc)
    _log_event(db, claim, actor, "SUBMITTED", f"Submission #{claim.submission_no}, cycle {claim.cycle_no}")
    db.commit()
    db.refresh(claim)
    return claim


def _advance_claim_status_after(claim: Claim, decided_step: ApprovalStep) -> None:
    remaining = [
        s
        for s in claim.approval_steps
        if s.cycle_no == claim.cycle_no and s.sequence > decided_step.sequence and s.status == ApprovalStepStatus.PENDING
    ]
    next_step = remaining[0] if remaining else None
    if next_step is None:
        return  # nothing left; verify_step() will have already set VERIFIED for the finance step
    if next_step.step_type == ApprovalStepType.FINANCE_VERIFICATION:
        claim.status = ClaimStatus.PENDING_FINANCE
    else:
        claim.status = ClaimStatus.PENDING_APPROVAL


def approve_step(db: Session, claim: Claim, actor: Employee, remarks: str | None = None) -> Claim:
    step = current_step(claim)
    if step is None:
        raise WorkflowError("No pending approval step on this claim")
    if step.assigned_to_code != actor.emp_code:
        raise WorkflowError("This claim is not awaiting your action")
    if step.assigned_to_code == claim.employee_code:
        # Defence-in-depth: routing should never produce this, but never let
        # a claimant approve their own claim — policy 2.2.
        raise WorkflowError("An approver cannot approve their own claim")

    step.status = ApprovalStepStatus.APPROVED
    step.remarks = remarks
    step.decided_at = datetime.now(timezone.utc)

    if step.step_type == ApprovalStepType.FINANCE_VERIFICATION:
        claim.status = ClaimStatus.VERIFIED
        _schedule_payment(db, claim)
        _log_event(db, claim, actor, "FINANCE_VERIFIED", remarks)
    else:
        _advance_claim_status_after(claim, step)
        _log_event(db, claim, actor, "APPROVED", remarks)

    db.commit()
    db.refresh(claim)
    return claim


def reject_step(db: Session, claim: Claim, actor: Employee, remarks: str) -> Claim:
    step = current_step(claim)
    if step is None:
        raise WorkflowError("No pending approval step on this claim")
    if step.assigned_to_code != actor.emp_code:
        raise WorkflowError("This claim is not awaiting your action")
    if not remarks or not remarks.strip():
        raise WorkflowError("Remarks are required to reject a claim")

    step.status = ApprovalStepStatus.REJECTED
    step.remarks = remarks
    step.decided_at = datetime.now(timezone.utc)
    claim.status = ClaimStatus.REJECTED
    _cancel_remaining_steps(claim, step, "Claim was rejected at an earlier step")
    _log_event(db, claim, actor, "REJECTED", remarks)
    db.commit()
    db.refresh(claim)
    return claim


def return_step(db: Session, claim: Claim, actor: Employee, remarks: str) -> Claim:
    """Policy 2.3 — return with remarks instead of approving/rejecting."""
    step = current_step(claim)
    if step is None:
        raise WorkflowError("No pending approval step on this claim")
    if step.assigned_to_code != actor.emp_code:
        raise WorkflowError("This claim is not awaiting your action")
    if not remarks or not remarks.strip():
        raise WorkflowError("Remarks are required to return a claim")

    step.status = ApprovalStepStatus.RETURNED
    step.remarks = remarks
    step.decided_at = datetime.now(timezone.utc)
    claim.status = ClaimStatus.RETURNED
    _cancel_remaining_steps(claim, step, "Claim was returned at an earlier step")
    _log_event(db, claim, actor, "RETURNED", remarks)
    db.commit()
    db.refresh(claim)
    return claim


def resubmit_claim(db: Session, claim: Claim, travel_request: TravelRequest, claimant: Employee, actor: Employee) -> Claim:
    """Policy 2.3 — same Travel Request ID, editable, resubmitted. Approvals
    restart at level 1 because an edit can move the claim into a different
    value band (see the plan's delivery-note assumption on this).
    """
    if claim.status != ClaimStatus.RETURNED:
        raise WorkflowError(f"Only a RETURNED claim can be resubmitted, not {claim.status}")

    blocking = policy_engine.has_blocking_flags(claim)
    if blocking:
        codes = ", ".join(sorted({f.code for f in blocking}))
        raise WorkflowError(f"Claim still has unresolved blocking issues: {codes}")

    policy_engine.compute_claim_totals(claim, advance_amount=float(travel_request.advance.amount) if travel_request.advance else 0)

    claim.submission_no += 1
    claim.cycle_no += 1
    claim.status = ClaimStatus.PENDING_APPROVAL
    claim.submitted_at = datetime.now(timezone.utc)

    build_approval_steps(db, claim, travel_request, claimant)
    _log_event(db, claim, actor, "RESUBMITTED", f"Submission #{claim.submission_no}, cycle {claim.cycle_no}")
    db.commit()
    db.refresh(claim)
    return claim


def _schedule_payment(db: Session, claim: Claim) -> None:
    day1 = int(policy_engine.get_config_raw(db, "PAYMENT_RUN_DAY_1"))
    day2 = int(policy_engine.get_config_raw(db, "PAYMENT_RUN_DAY_2"))
    today = date.today()
    for day in sorted([day1, day2]):
        if today.day <= day:
            scheduled = today.replace(day=day)
            break
    else:
        # Past both run days this month — roll to day1 next month.
        year = today.year + (1 if today.month == 12 else 0)
        month = 1 if today.month == 12 else today.month + 1
        scheduled = date(year, month, day1)

    db.add(
        Payment(
            claim_id=claim.id,
            amount=claim.amount_payable,
            scheduled_run_date=scheduled,
            status=PaymentStatus.SCHEDULED,
        )
    )


def release_payment(db: Session, claim: Claim, actor: Employee, reference: str) -> Claim:
    if claim.status != ClaimStatus.VERIFIED:
        raise WorkflowError(f"Only a VERIFIED claim can be paid, not {claim.status}")
    if not claim.payment:
        raise WorkflowError("No payment scheduled for this claim")

    claim.payment.status = PaymentStatus.PAID
    claim.payment.paid_at = datetime.now(timezone.utc)
    claim.payment.reference = reference
    claim.status = ClaimStatus.PAID
    _log_event(db, claim, actor, "PAID", f"Reference {reference}")
    db.commit()
    db.refresh(claim)
    return claim
