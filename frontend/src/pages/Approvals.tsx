import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApprovalsApi } from "../api/endpoints";
import { ClaimReviewPanel } from "../components/ClaimReviewPanel";
import { inr } from "../lib/format";
import type { Claim } from "../types";

function ClaimActionCard({ claim, defaultOpen }: { claim: Claim; defaultOpen: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(defaultOpen);
  const [remarks, setRemarks] = useState("");
  const [mode, setMode] = useState<"idle" | "reject" | "return">("idle");

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["approvals-queue"] });
    qc.invalidateQueries({ queryKey: ["dashboard-summary"] });
    qc.invalidateQueries({ queryKey: ["claim", claim.id] });
  };

  const approve = useMutation({
    mutationFn: () => ApprovalsApi.approve(claim.id, remarks || undefined),
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: () => ApprovalsApi.reject(claim.id, remarks),
    onSuccess: invalidate,
  });
  const returnClaim = useMutation({
    mutationFn: () => ApprovalsApi.return(claim.id, remarks),
    onSuccess: invalidate,
  });

  return (
    <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full flex-wrap items-center justify-between gap-3 px-5 py-4 text-left hover:bg-slate-50"
      >
        <div>
          <div className="font-semibold text-slate-800">{claim.travel_request_no}</div>
          <div className="text-xs text-slate-500">
            {claim.employee_name} · {(claim.current_step_role ?? "").replaceAll("_", " ")}
          </div>
        </div>
        <div className="flex items-center gap-6 text-sm">
          <div>
            <div className="text-[11px] text-slate-400">Disallowed</div>
            <div className="font-medium text-red-600">{inr(claim.total_disallowed)}</div>
          </div>
          <div>
            <div className="text-[11px] text-slate-400">Advance</div>
            <div className="font-medium">{inr(claim.advance_drawn)}</div>
          </div>
          <div className="text-right">
            <div className="text-[11px] text-slate-400">Net reimbursable</div>
            <div className="font-semibold text-slate-800">{inr(claim.net_reimbursable)}</div>
          </div>
          <span className="text-xs text-slate-400">{open ? "Hide details" : "Show details"}</span>
        </div>
      </button>

      {open && (
        <div className="border-t px-5 py-4">
          <ClaimReviewPanel claimId={claim.id} summary={claim} />
        </div>
      )}

      <div className="border-t bg-slate-50 px-5 py-3">
        {mode !== "idle" && (
          <textarea
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder={mode === "reject" ? "Reason for rejection (required)" : "Remarks for the employee (required)"}
            className="mb-3 w-full rounded border bg-white px-3 py-2 text-sm"
            rows={2}
          />
        )}
        <div className="flex flex-wrap gap-2">
          {mode === "idle" ? (
            <>
              <button
                onClick={() => approve.mutate()}
                disabled={approve.isPending}
                className="rounded bg-emerald-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
              >
                Approve
              </button>
              <button
                onClick={() => setMode("return")}
                className="rounded bg-orange-500 px-4 py-1.5 text-xs font-semibold text-white hover:bg-orange-600"
              >
                Return with remarks
              </button>
              <button
                onClick={() => setMode("reject")}
                className="rounded bg-red-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-red-700"
              >
                Reject
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => (mode === "reject" ? reject.mutate() : returnClaim.mutate())}
                disabled={!remarks.trim() || reject.isPending || returnClaim.isPending}
                className="rounded bg-slate-800 px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
              >
                Confirm {mode}
              </button>
              <button onClick={() => setMode("idle")} className="rounded px-4 py-1.5 text-xs text-slate-500">
                Cancel
              </button>
            </>
          )}
        </div>
        {(approve.isError || reject.isError || returnClaim.isError) && (
          <p className="mt-2 text-xs text-red-600">Action failed — please refresh and try again.</p>
        )}
      </div>
    </div>
  );
}

export function ApprovalsPage() {
  const { data: queue } = useQuery({ queryKey: ["approvals-queue"], queryFn: ApprovalsApi.myQueue });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold text-slate-800">Claims awaiting your approval</h1>
        <p className="text-sm text-slate-500">
          Review the policy-checked lines before you act. You cannot approve your own claim; returning a claim
          sends it back against the same Travel Request ID (policy 2.2 / 2.3).
        </p>
      </div>
      {queue?.length === 0 && (
        <div className="rounded-xl border bg-white p-8 text-center text-sm text-slate-400">
          Nothing is waiting on you right now.
        </div>
      )}
      {queue?.map((c, i) => (
        <ClaimActionCard key={c.id} claim={c} defaultOpen={i === 0} />
      ))}
    </div>
  );
}
