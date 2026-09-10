"""Manual verification for the routing/workflow engine: the Suresh Iyer
double-level case (policy 2.2) end to end through submit -> approve x2 ->
finance verify -> pay, plus a return/resubmit cycle (policy 2.3).

Run with: backend/.venv/bin/python -m scripts.smoke_test_workflow
"""
from datetime import date

from app.database import SessionLocal
from app.models import Advance, Claim, Employee, TravelRequest
from app.models.enums import ApprovalStepStatus, ClaimStatus, TravelRequestStatus
from app.services import workflow


def main() -> None:
    db = SessionLocal()

    suresh = db.get(Employee, "NX-2210")
    assert suresh is not None

    tr = db.query(TravelRequest).filter(TravelRequest.travel_request_no == "TRQ-2026-9001").first()
    if tr is None:
        tr = TravelRequest(
            travel_request_no="TRQ-2026-9001",
            employee_code=suresh.emp_code,
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 3),
            visiting_place="Mumbai HQ",
            city="Mumbai",
            purpose="Quarterly review",
            mode_of_travel="Flight",
            is_international=False,
            estimated_total=40000,
            advance_requested=0,
            status=TravelRequestStatus.APPROVED,
        )
        db.add(tr)
        db.flush()
        db.add(Advance(travel_request_id=tr.id, reference="ADV/TEST/9001", amount=0))
        db.flush()

    claim = db.query(Claim).filter(Claim.travel_request_id == tr.id).first()
    if claim is None:
        claim = Claim(travel_request_id=tr.id, employee_code=suresh.emp_code)
        db.add(claim)
        db.flush()
    claim.total_employee_paid = 40000  # BAND_2: Reporting Manager, Head of Department
    claim.status = ClaimStatus.DRAFT
    claim.lines.clear()
    db.commit()
    db.refresh(claim)

    claim = workflow.submit_claim(db, claim, tr, suresh, actor=suresh)

    business_steps = sorted(
        [s for s in claim.approval_steps if s.cycle_no == claim.cycle_no], key=lambda s: s.sequence
    )
    print("Resolved chain for Suresh Iyer's claim (band 25,001-75,000 -> RM, HoD):")
    for s in business_steps:
        print(f"  seq={s.sequence} role={s.role_code:20} assigned_to={s.assigned_to_code} status={s.status} skip_reason={s.skip_reason}")

    level1, level2, finance_step = business_steps[0], business_steps[1], business_steps[2]
    assert level1.assigned_to_code == "NX-1108", f"expected Meera Krishnan at level 1, got {level1.assigned_to_code}"
    assert level2.assigned_to_code == "NX-1002", f"expected Arvind Rao at level 2, got {level2.assigned_to_code}"
    assert level1.assigned_to_code != level2.assigned_to_code, "the same person must never be asked to act twice"
    assert finance_step.role_code == "FINANCE"

    meera = db.get(Employee, "NX-1108")
    arvind = db.get(Employee, "NX-1002")
    ravi = db.get(Employee, "NX-3305")

    claim = workflow.approve_step(db, claim, actor=meera, remarks="Looks fine")
    assert claim.status == ClaimStatus.PENDING_APPROVAL
    claim = workflow.approve_step(db, claim, actor=arvind, remarks="Approved")
    assert claim.status == ClaimStatus.PENDING_FINANCE
    claim = workflow.approve_step(db, claim, actor=ravi, remarks="Verified")
    assert claim.status == ClaimStatus.VERIFIED
    assert claim.payment is not None and claim.payment.status == "SCHEDULED"

    claim = workflow.release_payment(db, claim, actor=ravi, reference="PAY/TEST/0001")
    assert claim.status == ClaimStatus.PAID
    print("\nApprove -> Finance -> Pay lifecycle: OK")

    # --- Return / resubmit cycle (policy 2.3) ---------------------------
    claim2 = Claim(travel_request_id=tr.id, employee_code=suresh.emp_code, total_employee_paid=40000)
    db.add(claim2)
    db.commit()
    db.refresh(claim2)

    claim2 = workflow.submit_claim(db, claim2, tr, suresh, actor=suresh)
    step1 = workflow.current_step(claim2)
    assert step1.assigned_to_code == "NX-1108"
    claim2 = workflow.return_step(db, claim2, actor=meera, remarks="Please attach the missing bill")
    assert claim2.status == ClaimStatus.RETURNED
    assert claim2.submission_no == 1
    assert claim2.travel_request_id == tr.id, "must stay against the same Travel Request ID"

    claim2 = workflow.resubmit_claim(db, claim2, tr, suresh, actor=suresh)
    assert claim2.submission_no == 2
    assert claim2.cycle_no == 2
    new_step1 = workflow.current_step(claim2)
    assert new_step1.assigned_to_code == "NX-1108", "resubmission must restart at level 1"

    old_cycle_steps = [s for s in claim2.approval_steps if s.cycle_no == 1]
    assert any(s.status == ApprovalStepStatus.RETURNED for s in old_cycle_steps), "cycle 1 history must be preserved, not overwritten"
    print("Return -> same TRQ -> resubmit -> restarts at level 1, cycle 1 history preserved: OK")

    print("\nAll workflow assertions passed.")
    db.close()


if __name__ == "__main__":
    main()
