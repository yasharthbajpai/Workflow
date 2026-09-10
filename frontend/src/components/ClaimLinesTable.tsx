import { useState } from "react";
import type { ClaimLine } from "../types";
import { inr, shortDate } from "../lib/format";

const SEVERITY_STYLE: Record<string, string> = {
  BLOCK: "bg-red-100 text-red-700 border-red-200",
  WARN: "bg-amber-100 text-amber-700 border-amber-200",
  INFO: "bg-slate-100 text-slate-600 border-slate-200",
};

function AttendeeFixForm({
  onSave,
}: {
  onSave: (names: string[], org: string) => void;
}) {
  const [names, setNames] = useState("");
  const [org, setOrg] = useState("");
  return (
    <div className="mt-2 flex flex-wrap items-end gap-2 rounded-md bg-red-50 p-2">
      <div>
        <label className="block text-[10px] text-red-700">Attendee names (comma separated)</label>
        <input
          value={names}
          onChange={(e) => setNames(e.target.value)}
          placeholder="Rajesh Kumar, Anita Verma"
          className="w-56 rounded border border-red-200 px-2 py-1 text-xs"
        />
      </div>
      <div>
        <label className="block text-[10px] text-red-700">Organisation</label>
        <input
          value={org}
          onChange={(e) => setOrg(e.target.value)}
          placeholder="Vertex Technologies"
          className="w-40 rounded border border-red-200 px-2 py-1 text-xs"
        />
      </div>
      <button
        className="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
        disabled={!names.trim() || !org.trim()}
        onClick={() =>
          onSave(
            names.split(",").map((n) => n.trim()).filter(Boolean),
            org.trim()
          )
        }
      >
        Save &amp; resolve
      </button>
    </div>
  );
}

export function ClaimLinesTable({
  lines,
  editable,
  onPatchLine,
}: {
  lines: ClaimLine[];
  editable: boolean;
  onPatchLine?: (lineId: number, payload: Record<string, unknown>) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-slate-400">
            <th className="py-2">Section</th>
            <th>Description</th>
            <th>Date</th>
            <th>Paid by</th>
            <th className="text-right">Gross</th>
            <th className="text-right">Allowed</th>
            <th className="text-right">Disallowed</th>
            <th>Flags</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr
              key={line.id}
              className={`border-b align-top ${line.excluded ? "opacity-40" : ""} ${
                line.needs_review ? "bg-amber-50/60" : ""
              }`}
            >
              <td className="py-2 text-xs font-medium text-slate-500">{line.section}</td>
              <td className="max-w-xs">
                <div className="font-medium text-slate-800">{line.description}</div>
                <div className="text-xs text-slate-400">{line.head}</div>
                {line.disallowed_reason && (
                  <div className="mt-1 text-xs text-red-600">{line.disallowed_reason}</div>
                )}
                {editable &&
                  onPatchLine &&
                  line.flags.some((f) => f.code === "BE_MISSING_ATTENDEES") && (
                    <AttendeeFixForm
                      onSave={(names, org) =>
                        onPatchLine(line.id, {
                          attendee_names: names,
                          attendee_org: org,
                          clear_flag_codes: ["BE_MISSING_ATTENDEES"],
                        })
                      }
                    />
                  )}
              </td>
              <td className="text-xs text-slate-500">{shortDate(line.txn_date)}</td>
              <td className="text-xs">{line.paid_by}</td>
              <td className="text-right">{inr(line.gross_amount)}</td>
              <td className="text-right text-emerald-700">{inr(line.allowed_amount)}</td>
              <td className="text-right text-red-600">{inr(line.disallowed_amount)}</td>
              <td className="max-w-[220px]">
                <div className="flex flex-col gap-1">
                  {line.flags.map((f) => (
                    <span
                      key={f.id}
                      title={f.message}
                      className={`w-fit rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                        SEVERITY_STYLE[f.severity]
                      }`}
                    >
                      {f.severity} · {f.code} (policy {f.policy_ref})
                    </span>
                  ))}
                  {line.excluded && (
                    <span className="w-fit rounded border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                      excluded from totals
                    </span>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
