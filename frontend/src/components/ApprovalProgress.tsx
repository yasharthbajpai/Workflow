import type { ApprovalStep } from "../types";

const STATUS_STYLE: Record<string, string> = {
  APPROVED: "bg-emerald-500 text-white",
  PENDING: "bg-amber-400 text-white",
  REJECTED: "bg-red-500 text-white",
  RETURNED: "bg-orange-500 text-white",
  SKIPPED: "bg-slate-300 text-slate-600",
};

const STATUS_LABEL: Record<string, string> = {
  APPROVED: "Approved",
  PENDING: "Pending",
  REJECTED: "Rejected",
  RETURNED: "Returned",
  SKIPPED: "Skipped",
};

function roleLabel(roleCode: string, stepType: string): string {
  if (stepType === "FINANCE_VERIFICATION") return "Finance verify";
  const map: Record<string, string> = {
    REPORTING_MANAGER: "Reporting Manager",
    HOD: "Head of Department",
    HOD_DIVISION: "Head of Division",
    MD: "MD / CEO",
  };
  return map[roleCode] ?? roleCode;
}

/**
 * Horizontal segmented progress bar for a claim's full lifecycle: every
 * business approval level, Finance verification, and payment — one segment
 * per ApprovalStep, colour-coded by state, with a "Skipped, policy 2.2"
 * badge whenever routing had to escalate past someone (see
 * app/services/routing.py resolve_approval_chain).
 */
export function ApprovalProgress({
  steps,
  cycleNo,
  paid,
}: {
  steps: ApprovalStep[];
  cycleNo: number;
  paid: boolean;
}) {
  const current = steps.filter((s) => s.cycle_no === cycleNo).sort((a, b) => a.sequence - b.sequence);
  const segments = [
    ...current.map((s) => ({
      key: `step-${s.id}`,
      label: roleLabel(s.role_code, s.step_type),
      status: s.status,
      sub: s.skip_reason ? "Skipped — policy 2.2" : s.assigned_to_name ?? undefined,
      remarks: s.remarks,
    })),
    {
      key: "payment",
      label: "Payment",
      status: paid ? "APPROVED" : "PENDING",
      sub: paid ? undefined : "Awaiting payment run (10th/25th)",
      remarks: null as string | null,
    },
  ];

  return (
    <div className="w-full">
      <div className="flex w-full items-stretch gap-1">
        {segments.map((seg) => (
          <div key={seg.key} className="flex-1 min-w-0">
            <div
              title={seg.remarks ?? seg.sub ?? seg.label}
              className={`h-2.5 rounded-full ${STATUS_STYLE[seg.status] ?? "bg-slate-200"}`}
            />
            <div className="mt-1.5 truncate text-[11px] font-medium text-slate-700">{seg.label}</div>
            <div className="truncate text-[10px] text-slate-400">
              {seg.sub ?? STATUS_LABEL[seg.status] ?? seg.status}
            </div>
          </div>
        ))}
      </div>
      {cycleNo > 1 && (
        <p className="mt-2 text-[11px] text-orange-600">
          Resubmission #{cycleNo} — a prior cycle was returned for correction (policy 2.3). Approvals restarted at
          level 1.
        </p>
      )}
    </div>
  );
}
