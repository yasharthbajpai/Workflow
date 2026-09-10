"""Approval routing — clauses 2.1, 2.2, 2.3 of expense_policy.md.

2.1  Finance verification is appended unconditionally as the terminal
     business step, on every claim, regardless of value. It is never part
     of a value band.

2.2  An approver cannot approve their own claim, and where one person would
     otherwise be asked to act at two levels, the second level escalates to
     the next person up. Implemented by walking the reporting_manager_code
     chain one step per required level, always continuing past anyone
     already claimant/already-assigned before landing on this level's
     approver (see resolve_approval_chain). In this pack's org chart that
     walk never needs to skip anyone (the hierarchy already has exactly one
     person per level), but the loop is written to handle the general case
     — e.g. Suresh Iyer claiming and Meera Krishnan being both "the RM
     level" and nominally the HOD: level 1 lands on Meera, level 2 walks
     from Meera and lands on Arvind Rao, never repeating Meera.

2.3  Handled in app/services/workflow.py (return_claim / resubmit_claim),
     not here — this module only ever resolves a fresh chain for a given
     claimed amount.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApprovalBand, Employee
from app.services.policy_engine import get_config_raw


@dataclass
class ResolvedStep:
    sequence: int
    role_code: str
    assigned_to: Employee | None
    skip_reason: str | None


def select_approval_band(db: Session, amount: float, is_international: bool) -> ApprovalBand:
    if is_international:
        band = db.scalar(select(ApprovalBand).where(ApprovalBand.international_only.is_(True)))
        if band:
            return band
    bands = db.scalars(
        select(ApprovalBand).where(ApprovalBand.international_only.is_(False)).order_by(ApprovalBand.min_amount)
    ).all()
    for band in bands:
        lo = float(band.min_amount)
        hi = float(band.max_amount) if band.max_amount is not None else float("inf")
        if lo <= amount <= hi:
            return band
    return bands[-1]  # amount above every band's max -> highest band


def resolve_approval_chain(db: Session, claimant: Employee, required_levels: list[str]) -> list[ResolvedStep]:
    used_codes = {claimant.emp_code}
    pointer = claimant
    steps: list[ResolvedStep] = []

    for idx, role_code in enumerate(required_levels, start=1):
        direct_manager_code = pointer.reporting_manager_code
        walker = pointer
        candidate: Employee | None = None
        skipped_any = False

        while True:
            mgr_code = walker.reporting_manager_code
            if not mgr_code:
                candidate = None
                break
            manager = db.get(Employee, mgr_code)
            if manager is None:
                candidate = None
                break
            if manager.emp_code in used_codes:
                walker = manager
                skipped_any = True
                continue
            candidate = manager
            break

        if candidate is None:
            steps.append(
                ResolvedStep(
                    sequence=idx,
                    role_code=role_code,
                    assigned_to=None,
                    skip_reason="No eligible approver available above the claimant for this level",
                )
            )
            continue

        skip_reason = None
        if skipped_any or candidate.emp_code != direct_manager_code:
            skip_reason = (
                f"Normal {role_code} approver was already assigned an earlier level or is the claimant; "
                f"escalated to {candidate.name} — policy 2.2"
            )

        steps.append(ResolvedStep(sequence=idx, role_code=role_code, assigned_to=candidate, skip_reason=skip_reason))
        used_codes.add(candidate.emp_code)
        pointer = candidate

    return steps


def finance_verifier(db: Session) -> Employee:
    emp_code = get_config_raw(db, "FINANCE_VERIFIER_EMP_CODE")
    employee = db.get(Employee, emp_code)
    if not employee:
        raise ValueError(f"Configured Finance verifier {emp_code} not found")
    return employee
