import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ClaimsApi } from "../api/endpoints";
import { ApprovalProgress } from "./ApprovalProgress";
import { ClaimLinesTable } from "./ClaimLinesTable";
import { SettlementSummary } from "./SettlementSummary";
import type { Claim } from "../types";

export function ClaimReviewPanel({
  claimId,
  summary,
}: {
  claimId: number;
  /** Queue-row totals shown immediately while the full claim loads. */
  summary?: Claim;
}) {
  const { data: claim, isLoading, isError } = useQuery({
    queryKey: ["claim", claimId],
    queryFn: () => ClaimsApi.get(claimId),
  });

  const view = claim ?? summary;
  if (!view) {
    return <div className="text-sm text-slate-400">Loading claim…</div>;
  }

  const flagCount =
    claim?.lines.reduce((n, l) => n + l.flags.length, 0) ?? 0;
  const warnOrBlock =
    claim?.lines.filter((l) => l.flags.some((f) => f.severity === "BLOCK" || f.severity === "WARN")).length ?? 0;
  const excluded = claim?.lines.filter((l) => l.excluded).length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to={`/claims/${view.id}`} className="text-base font-semibold text-slate-800 hover:underline">
            {view.travel_request_no}
          </Link>
          <p className="text-sm text-slate-500">
            {view.employee_name} · {view.employee_code} · submission #{view.submission_no} ·{" "}
            {view.status.replaceAll("_", " ")}
          </p>
        </div>
        {claim && (
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">
              {claim.lines.length} lines
            </span>
            {excluded > 0 && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{excluded} excluded</span>
            )}
            {warnOrBlock > 0 && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">
                {warnOrBlock} lines flagged
              </span>
            )}
            {flagCount > 0 && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{flagCount} policy flags</span>
            )}
          </div>
        )}
      </div>

      {claim?.approval_steps?.length ? (
        <ApprovalProgress
          steps={claim.approval_steps}
          cycleNo={claim.cycle_no}
          paid={claim.status === "PAID"}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-lg border bg-slate-50 p-4 lg:col-span-1">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Settlement</h3>
          <div className="mt-2">
            <SettlementSummary claim={view} />
          </div>
        </div>
        <div className="lg:col-span-2">
          {isLoading && !claim && <p className="text-sm text-slate-400">Loading line items…</p>}
          {isError && (
            <p className="text-sm text-red-600">Could not load claim lines. Open the claim page to review.</p>
          )}
          {claim && (
            <>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Line items (policy-checked)
              </h3>
              <ClaimLinesTable lines={claim.lines} editable={false} />
            </>
          )}
        </div>
      </div>

      {claim && claim.events.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">History</h3>
          <ul className="space-y-2 text-sm">
            {claim.events.map((e) => (
              <li key={e.id} className="border-l-2 border-slate-200 pl-3">
                <span className="font-medium text-slate-800">{e.event_type.replaceAll("_", " ")}</span>
                <span className="text-xs text-slate-400">
                  {" "}
                  · {new Date(e.created_at).toLocaleString("en-IN")}
                  {e.actor_code ? ` · ${e.actor_code}` : ""}
                </span>
                {e.detail && <div className="text-xs text-slate-500">{e.detail}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
