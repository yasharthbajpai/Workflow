import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ClaimsApi, TravelRequestsApi } from "../api/endpoints";
import { ClaimLinesTable } from "../components/ClaimLinesTable";
import { TravelRequestForm } from "../components/TravelRequestForm";
import { inr, shortDate } from "../lib/format";
import type { ClaimDetail } from "../types";

export function SubmitPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: travelRequests, refetch } = useQuery({ queryKey: ["travel-requests-mine"], queryFn: TravelRequestsApi.mine });
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [activeTrId, setActiveTrId] = useState<number | null>(null);

  const scan = useMutation({
    mutationFn: (trId: number) => TravelRequestsApi.scan(trId),
    onSuccess: (data, trId) => {
      setClaim(data);
      setActiveTrId(trId);
    },
  });

  const patchLine = useMutation({
    mutationFn: ({ lineId, payload }: { lineId: number; payload: Record<string, unknown> }) =>
      ClaimsApi.patchLine(claim!.id, lineId, payload),
    onSuccess: (data) => setClaim(data),
  });

  const submit = useMutation({
    mutationFn: () => ClaimsApi.submit(claim!.id),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["claims-mine"] });
      qc.invalidateQueries({ queryKey: ["dashboard-summary"] });
      navigate(`/claims/${data.id}`);
    },
  });

  const blockingFlags = claim?.lines.filter((l) => !l.excluded && l.flags.some((f) => f.severity === "BLOCK")) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-slate-800">Submit a travel expense claim</h1>
        <p className="text-sm text-slate-500">
          Pick a travel request, scan the inbox for it, review what the AI extracted, then submit.
          To try filling the form from scratch, log in as{" "}
          <span className="font-medium text-slate-700">imran.qureshi@nortexindustries.com</span>{" "}
          (password <span className="font-medium text-slate-700">Nortex@123</span>) — he has a
          fake Hyderabad inbox waiting.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        {travelRequests?.map((tr) => (
          <div
            key={tr.id}
            className={`w-72 rounded-xl border bg-white p-4 shadow-sm ${
              activeTrId === tr.id ? "border-blue-400 ring-1 ring-blue-200" : ""
            }`}
          >
            <div className="text-sm font-semibold text-slate-800">{tr.travel_request_no}</div>
            <div className="text-xs text-slate-500">{tr.visiting_place}</div>
            <div className="mt-1 text-xs text-slate-400">
              {shortDate(tr.from_date)} → {shortDate(tr.to_date)}
            </div>
            <button
              onClick={() => scan.mutate(tr.id)}
              disabled={scan.isPending}
              className="mt-3 w-full rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {scan.isPending && scan.variables === tr.id ? "Scanning…" : "Scan my inbox with AI"}
            </button>
          </div>
        ))}
      </div>

      <TravelRequestForm onCreated={() => refetch()} />

      {claim && (
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-slate-700">Extracted claim lines</h2>
              <p className="text-xs text-slate-400">
                {claim.lines.length} lines found. Excluded/duplicate lines are greyed out but kept for the audit
                trail.
              </p>
            </div>
            <div className="text-right">
              <div className="text-xs text-slate-400">Net reimbursable</div>
              <div className="text-lg font-bold text-slate-800">{inr(claim.net_reimbursable)}</div>
            </div>
          </div>

          <div className="mt-4">
            <ClaimLinesTable
              lines={claim.lines}
              editable
              onPatchLine={(lineId, payload) => patchLine.mutate({ lineId, payload })}
            />
          </div>

          {blockingFlags.length > 0 && (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              This claim cannot be submitted yet — resolve the BLOCK flags above first (e.g. supply attendee names
              for business entertainment, or attach a missing proof).
            </div>
          )}

          <div className="mt-4 grid grid-cols-2 gap-4 rounded-md bg-slate-50 p-4 text-sm md:grid-cols-4">
            <div>
              <div className="text-xs text-slate-400">Company-paid (memo)</div>
              <div className="font-semibold">{inr(claim.total_company_paid)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Disallowed</div>
              <div className="font-semibold text-red-600">{inr(claim.total_disallowed)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Advance drawn</div>
              <div className="font-semibold">{inr(claim.advance_drawn)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">
                {claim.amount_recoverable > 0 ? "Recoverable from employee" : "Payable to employee"}
              </div>
              <div className="font-semibold text-emerald-700">
                {inr(claim.amount_recoverable > 0 ? claim.amount_recoverable : claim.amount_payable)}
              </div>
            </div>
          </div>

          <button
            onClick={() => submit.mutate()}
            disabled={submit.isPending || blockingFlags.length > 0}
            className="mt-4 rounded-md bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
          >
            {submit.isPending ? "Submitting…" : "Submit claim for approval"}
          </button>
          {submit.isError && (
            <p className="mt-2 text-sm text-red-600">
              {(submit.error as any)?.response?.data?.detail ?? "Could not submit claim"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
