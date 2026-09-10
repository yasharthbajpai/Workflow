import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ClaimsApi, DashboardApi } from "../api/endpoints";
import { StageBarChart } from "../components/StageBarChart";
import { inr } from "../lib/format";

export function DashboardPage() {
  const { data: summary } = useQuery({ queryKey: ["dashboard-summary"], queryFn: DashboardApi.summary });
  const { data: myClaims } = useQuery({ queryKey: ["claims-mine"], queryFn: ClaimsApi.mine });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="text-xs font-medium text-slate-500">My claims</div>
          <div className="mt-1 text-2xl font-bold text-slate-800">{summary?.my_claims_count ?? "—"}</div>
        </div>
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="text-xs font-medium text-slate-500">Awaiting my action</div>
          <div className="mt-1 text-2xl font-bold text-amber-600">{summary?.awaiting_my_action_count ?? "—"}</div>
        </div>
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="text-xs font-medium text-slate-500">Total claims tracked</div>
          <div className="mt-1 text-2xl font-bold text-slate-800">
            {summary ? summary.stage_counts.reduce((a, b) => a + b.count, 0) : "—"}
          </div>
        </div>
      </div>

      <div className="rounded-xl border bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-700">Claims by workflow stage</h2>
        {summary && <StageBarChart data={summary.stage_counts} />}
      </div>

      <div className="rounded-xl border bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-700">My claims</h2>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400">
              <th className="py-2">Travel Request</th>
              <th>Status</th>
              <th>Net reimbursable</th>
              <th>Payable</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {myClaims?.map((c) => (
              <tr key={c.id} className="border-t">
                <td className="py-2">{c.travel_request_no}</td>
                <td>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                    {c.status.replace("_", " ")}
                  </span>
                </td>
                <td>{inr(c.net_reimbursable)}</td>
                <td>{inr(c.amount_payable)}</td>
                <td className="text-right">
                  <Link to={`/claims/${c.id}`} className="text-blue-600 hover:underline">
                    View
                  </Link>
                </td>
              </tr>
            ))}
            {myClaims?.length === 0 && (
              <tr>
                <td colSpan={5} className="py-4 text-center text-slate-400">
                  No claims yet — go to Submit to scan your inbox.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
