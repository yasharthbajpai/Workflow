import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApprovalsApi } from "../api/endpoints";
import { inr } from "../lib/format";
import type { Claim } from "../types";

function ClaimActionRow({ claim }: { claim: Claim }) {
  const qc = useQueryClient();
  const [remarks, setRemarks] = useState("");
  const [mode, setMode] = useState<"idle" | "reject" | "return">("idle");

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["approvals-queue"] });
    qc.invalidateQueries({ queryKey: ["dashboard-summary"] });
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
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link to={`/claims/${claim.id}`} className="font-semibold text-slate-800 hover:underline">
            {claim.travel_request_no}
          </Link>
          <div className="text-xs text-slate-400">
            {claim.employee_name} · {claim.current_step_role?.replace("_", " ")}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-400">Net reimbursable</div>
          <div className="font-semibold">{inr(claim.net_reimbursable)}</div>
        </div>
      </div>

      {mode !== "idle" && (
        <textarea
          value={remarks}
          onChange={(e) => setRemarks(e.target.value)}
          placeholder={mode === "reject" ? "Reason for rejection (required)" : "Remarks for the employee (required)"}
          className="mt-3 w-full rounded border px-3 py-2 text-sm"
          rows={2}
        />
      )}

      <div className="mt-3 flex gap-2">
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
  );
}

export function ApprovalsPage() {
  const { data: queue } = useQuery({ queryKey: ["approvals-queue"], queryFn: ApprovalsApi.myQueue });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold text-slate-800">Claims awaiting your approval</h1>
        <p className="text-sm text-slate-500">
          An approver can never approve their own claim, and returning a claim sends it back to the employee against
          the same Travel Request ID (policy 2.2 / 2.3).
        </p>
      </div>
      {queue?.length === 0 && (
        <div className="rounded-xl border bg-white p-8 text-center text-sm text-slate-400">
          Nothing is waiting on you right now.
        </div>
      )}
      {queue?.map((c) => <ClaimActionRow key={c.id} claim={c} />)}
    </div>
  );
}
