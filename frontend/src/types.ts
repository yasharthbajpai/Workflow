export interface Employee {
  emp_code: string;
  name: string;
  email: string;
  designation: string;
  department: string;
  cost_centre: string;
  city: string;
  role_code: string;
  reporting_manager_code: string | null;
  reporting_manager_name: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  employee: Employee;
}

export type BorneBy = "Employee" | "Company";

export interface EstimateLine {
  id: number;
  head: string;
  basis: string;
  estimate: number;
  borne_by: BorneBy;
}

export interface TravelRequest {
  id: number;
  travel_request_no: string;
  employee_code: string;
  from_date: string;
  to_date: string;
  visiting_place: string;
  city: string;
  purpose: string;
  mode_of_travel: string;
  is_international: boolean;
  estimated_total: number;
  advance_requested: number;
  status: string;
  estimate_lines: EstimateLine[];
}

export interface TravelRequestCreatePayload {
  from_date: string;
  to_date: string;
  visiting_place: string;
  city: string;
  purpose: string;
  mode_of_travel: string;
  is_international: boolean;
  advance_requested: number;
  estimate_lines: Omit<EstimateLine, "id">[];
}

export interface DocumentOut {
  id: number;
  filename: string;
  mime_type: string;
  sender: string | null;
  subject: string | null;
  doc_type: string | null;
  discarded: boolean;
  discard_reason: string | null;
  extraction_mode: string | null;
}

export interface LinePolicyFlag {
  id: number;
  code: string;
  severity: "BLOCK" | "WARN" | "INFO";
  policy_ref: string;
  message: string;
}

export interface ClaimLine {
  id: number;
  section: "LODGING" | "TRANSPORT" | "OTHER";
  head: string;
  txn_date: string | null;
  description: string;
  merchant: string | null;
  from_place: string | null;
  to_place: string | null;
  gross_amount: number;
  tax_amount: number;
  allowed_amount: number;
  disallowed_amount: number;
  disallowed_reason: string | null;
  paid_by: "Employee" | "Company";
  proof_document_id: number | null;
  proof_ref: string | null;
  source: string;
  confidence: number | null;
  needs_review: boolean;
  excluded: boolean;
  flags: LinePolicyFlag[];
}

export interface ApprovalStep {
  id: number;
  cycle_no: number;
  sequence: number;
  step_type: "BUSINESS" | "FINANCE_VERIFICATION";
  role_code: string;
  assigned_to_code: string | null;
  assigned_to_name: string | null;
  status: "PENDING" | "APPROVED" | "REJECTED" | "RETURNED" | "SKIPPED";
  skip_reason: string | null;
  remarks: string | null;
  decided_at: string | null;
}

export interface ClaimEvent {
  id: number;
  actor_code: string | null;
  event_type: string;
  detail: string | null;
  created_at: string;
}

export interface Payment {
  amount: number;
  scheduled_run_date: string | null;
  status: "SCHEDULED" | "PAID";
  paid_at: string | null;
  reference: string | null;
}

export type ClaimStatus =
  | "DRAFT"
  | "PENDING_APPROVAL"
  | "PENDING_FINANCE"
  | "RETURNED"
  | "REJECTED"
  | "VERIFIED"
  | "PAID";

export interface Claim {
  id: number;
  travel_request_id: number;
  travel_request_no: string | null;
  employee_code: string;
  employee_name: string | null;
  status: ClaimStatus;
  submission_no: number;
  cycle_no: number;
  submitted_at: string | null;
  total_employee_paid: number;
  total_company_paid: number;
  total_disallowed: number;
  net_reimbursable: number;
  advance_drawn: number;
  amount_payable: number;
  amount_recoverable: number;
  current_step_role: string | null;
  current_step_assigned_to: string | null;
}

export interface ClaimDetail extends Claim {
  lines: ClaimLine[];
  approval_steps: ApprovalStep[];
  events: ClaimEvent[];
  payment: Payment | null;
}

export interface DashboardSummary {
  my_claims_count: number;
  awaiting_my_action_count: number;
  stage_counts: { status: ClaimStatus; count: number }[];
}
