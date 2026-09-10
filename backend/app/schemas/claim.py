from datetime import date, datetime

from pydantic import BaseModel


class LinePolicyFlagOut(BaseModel):
    id: int
    code: str
    severity: str
    policy_ref: str
    message: str

    model_config = {"from_attributes": True}


class ClaimLineOut(BaseModel):
    id: int
    section: str
    head: str
    txn_date: date | None
    description: str
    merchant: str | None
    from_place: str | None
    to_place: str | None
    gross_amount: float
    tax_amount: float
    allowed_amount: float
    disallowed_amount: float
    disallowed_reason: str | None
    paid_by: str
    proof_document_id: int | None
    proof_ref: str | None
    source: str
    confidence: float | None
    needs_review: bool
    excluded: bool
    flags: list[LinePolicyFlagOut] = []

    model_config = {"from_attributes": True}


class ClaimLinePatch(BaseModel):
    description: str | None = None
    attendee_names: list[str] | None = None
    attendee_org: str | None = None
    gross_amount: float | None = None
    allowed_amount: float | None = None
    disallowed_amount: float | None = None
    disallowed_reason: str | None = None
    paid_by: str | None = None
    clear_flag_codes: list[str] = []


class ApprovalStepOut(BaseModel):
    id: int
    cycle_no: int
    sequence: int
    step_type: str
    role_code: str
    assigned_to_code: str | None
    assigned_to_name: str | None = None
    status: str
    skip_reason: str | None
    remarks: str | None
    decided_at: datetime | None

    model_config = {"from_attributes": True}


class ClaimEventOut(BaseModel):
    id: int
    actor_code: str | None
    event_type: str
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentOut(BaseModel):
    amount: float
    scheduled_run_date: date | None
    status: str
    paid_at: datetime | None
    reference: str | None

    model_config = {"from_attributes": True}


class ClaimOut(BaseModel):
    id: int
    travel_request_id: int
    travel_request_no: str | None = None
    employee_code: str
    employee_name: str | None = None
    status: str
    submission_no: int
    cycle_no: int
    submitted_at: datetime | None
    total_employee_paid: float
    total_company_paid: float
    total_disallowed: float
    net_reimbursable: float
    advance_drawn: float
    amount_payable: float
    amount_recoverable: float
    current_step_role: str | None = None
    current_step_assigned_to: str | None = None

    model_config = {"from_attributes": True}


class ClaimDetailOut(ClaimOut):
    lines: list[ClaimLineOut] = []
    approval_steps: list[ApprovalStepOut] = []
    events: list[ClaimEventOut] = []
    payment: PaymentOut | None = None


class ActionRequest(BaseModel):
    remarks: str | None = None


class PayRequest(BaseModel):
    reference: str
