import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { ClaimsApi } from "../api/endpoints";
import { ApprovalProgress } from "../components/ApprovalProgress";
import { ClaimLinesTable } from "../components/ClaimLinesTable";
import { inr, shortDate } from "../lib/format";
import { useAuth } from "../auth/AuthContext";

export function ClaimDetailPage() {
  const { id } = useParams();
  const claimId = Number(id);
  const qc = useQueryClient();
  const { employee } = useAuth();

  const { data: claim, isLoading } = useQuery({
    queryKey: ["claim", claimId],
    queryFn: () => ClaimsApi.get(claimId),
    enabled: Number.isFinite(claimId),
  });

  const patchLine = useMutation({
    mutationFn: ({ lineId, payload }: { lineId: number; payload: Record<string, unknown> }) =>
      ClaimsApi.patchLine(claimId, lineId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["claim", claimId] }),
  });

  const resubmit = useMutation({
    mutationFn: () => ClaimsApi.resubmit(claimId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["claim", claimId] });
      qc.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });

  if (isLoading || !claim) return <div className="text-sm text-slate-400">Loading…</div>;

  const isOwner = employee?.emp_code === claim.employee_code;
  const canResubmit = isOwner && claim.status === "RETURNED";
  const blockingFlags = claim.lines.filter((l) => !l.excluded && l.flags.some((f) => f.severity === "BLOCK"));

  const lastReturnEvent = [...claim.events].reverse().find((e) => e.event_type === "RETURNED");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-slate-800">{claim.travel_request_no}</h1>
          <p className="text-sm text-slate-500">
            {claim.employee_name} · Submission #{claim.submission_no} · Status{" "}
            <span className="font-medium text-slate-700">{claim.status.replace("_", " ")}</span>
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-400">Net reimbursable</div>
          <div className="text-xl font-bold text-slate-800">{inr(claim.net_reimbursable)}</div>
        </div>
      </div>

      <div className="rounded-xl border bg-white p-5 shadow-sm">
        <ApprovalProgress steps={claim.approval_steps} cycleNo={claim.cycle_no} paid={claim.status === "PAID"} />
      </div>

      {claim.status === "RETURNED" && lastReturnEvent && (
        <div className="rounded-md border border-orange-200 bg-orange-50 p-4 text-sm text-orange-800">
          <span className="font-semibold">Returned for correction:</span> {lastReturnEvent.detail}
        </div>
      )}

      <div className="rounded-xl border bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-700">Claim lines</h2>
        <div className="mt-3">
          <ClaimLinesTable
            lines={claim.lines}
            editable={canResubmit}
            onPatchLine={canResubmit ? (lineId, payload) => patchLine.mutate({ lineId, payload }) : undefined}
          />
        </div>

        {canResubmit && (
          <div className="mt-4">
            {blockingFlags.length > 0 && (
              <p className="mb-2 text-sm text-red-600">Resolve the BLOCK flags above before resubmitting.</p>
            )}
            <button
              onClick={() => resubmit.mutate()}
              disabled={resubmit.isPending || blockingFlags.length > 0}
              className="rounded-md bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
            >
              {resubmit.isPending ? "Resubmitting…" : "Resubmit against the same Travel Request ID"}
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-700">Settlement summary</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <Row label="Total paid by employee" value={inr(claim.total_employee_paid)} />
            <Row label="Total paid by company (memo)" value={inr(claim.total_company_paid)} />
            <Row label="Disallowed" value={inr(claim.total_disallowed)} valueClass="text-red-600" />
            <Row label="Net reimbursable" value={inr(claim.net_reimbursable)} bold />
            <Row label="Advance drawn" value={inr(claim.advance_drawn)} />
            <Row label="Amount payable" value={inr(claim.amount_payable)} valueClass="text-emerald-700" bold />
            <Row label="Amount recoverable" value={inr(claim.amount_recoverable)} valueClass="text-red-600" bold />
          </dl>
          {claim.payment && (
            <div className="mt-3 border-t pt-3 text-sm">
              <Row label="Payment status" value={claim.payment.status} />
              <Row label="Scheduled run" value={shortDate(claim.payment.scheduled_run_date)} />
              {claim.payment.reference && <Row label="Reference" value={claim.payment.reference} />}
            </div>
          )}
        </div>

        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-700">Event timeline</h2>
          <ul className="mt-3 space-y-3 text-sm">
            {claim.events.map((e) => (
              <li key={e.id} className="border-l-2 border-slate-200 pl-3">
                <div className="font-medium text-slate-800">{e.event_type.replace("_", " ")}</div>
                <div className="text-xs text-slate-400">
                  {new Date(e.created_at).toLocaleString("en-IN")} {e.actor_code ? `· ${e.actor_code}` : ""}
                </div>
                {e.detail && <div className="text-xs text-slate-500">{e.detail}</div>}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, bold, valueClass }: { label: string; value: string; bold?: boolean; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={`${bold ? "font-bold" : "font-medium"} ${valueClass ?? "text-slate-800"}`}>{value}</span>
    </div>
  );
}
