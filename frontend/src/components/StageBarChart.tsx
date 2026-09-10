import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ClaimStatus } from "../types";

const LABEL: Record<ClaimStatus, string> = {
  DRAFT: "Draft",
  PENDING_APPROVAL: "Pending approval",
  PENDING_FINANCE: "Pending finance",
  RETURNED: "Returned",
  REJECTED: "Rejected",
  VERIFIED: "Verified",
  PAID: "Paid",
};

const COLOR: Record<ClaimStatus, string> = {
  DRAFT: "#94a3b8",
  PENDING_APPROVAL: "#f59e0b",
  PENDING_FINANCE: "#3b82f6",
  RETURNED: "#f97316",
  REJECTED: "#ef4444",
  VERIFIED: "#10b981",
  PAID: "#059669",
};

export function StageBarChart({ data }: { data: { status: ClaimStatus; count: number }[] }) {
  const chartData = data.map((d) => ({ name: LABEL[d.status] ?? d.status, count: d.count, status: d.status }));
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 12, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-15} textAnchor="end" height={50} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {chartData.map((entry) => (
              <Cell key={entry.status} fill={COLOR[entry.status as ClaimStatus] ?? "#64748b"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
