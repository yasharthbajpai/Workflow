import type { Claim, Payment } from "../types";
import { inr, shortDate } from "../lib/format";

function Row({
  label,
  value,
  bold,
  valueClass,
}: {
  label: string;
  value: string;
  bold?: boolean;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-slate-500">{label}</span>
      <span className={`${bold ? "font-bold" : "font-medium"} ${valueClass ?? "text-slate-800"}`}>{value}</span>
    </div>
  );
}

export function SettlementSummary({
  claim,
}: {
  claim: Claim & { payment?: Payment | null };
}) {
  return (
    <dl className="space-y-2 text-sm">
      <Row label="Paid by employee" value={inr(claim.total_employee_paid)} />
      <Row label="Paid by company (memo)" value={inr(claim.total_company_paid)} />
      <Row label="Disallowed" value={inr(claim.total_disallowed)} valueClass="text-red-600" />
      <Row label="Net reimbursable" value={inr(claim.net_reimbursable)} bold />
      <Row label="Advance drawn" value={inr(claim.advance_drawn)} />
      <Row
        label="Amount payable"
        value={inr(claim.amount_payable)}
        valueClass="text-emerald-700"
        bold
      />
      <Row
        label="Amount recoverable"
        value={inr(claim.amount_recoverable)}
        valueClass="text-red-600"
        bold
      />
      {claim.payment && (
        <div className="border-t pt-2">
          <Row label="Payment status" value={claim.payment.status} />
          <Row label="Scheduled run" value={shortDate(claim.payment.scheduled_run_date)} />
          {claim.payment.reference && <Row label="Reference" value={claim.payment.reference} />}
        </div>
      )}
    </dl>
  );
}
