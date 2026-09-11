import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { TravelRequestsApi } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { inr } from "../lib/format";
import type { BorneBy, TravelRequestCreatePayload } from "../types";

const DEFAULT_HEADS: { head: string; basis: string; borne_by: BorneBy }[] = [
  { head: "Air / Rail", basis: "Return, economy", borne_by: "Company" },
  { head: "Lodging", basis: "", borne_by: "Company" },
  { head: "Local conveyance", basis: "Actuals", borne_by: "Employee" },
  { head: "Meals / allowance", basis: "As per policy", borne_by: "Employee" },
  { head: "Other", basis: "", borne_by: "Employee" },
];

const APPROVAL_ROWS = [
  { level: 1, role: "Reporting Manager" },
  { level: 2, role: "Head of Department" },
  { level: 3, role: "Head of Division" },
  { level: 4, role: "Finance" },
  { level: 5, role: "MD / CEO (if > policy limit)" },
];

type EstimateDraft = { head: string; basis: string; estimate: string; borne_by: BorneBy };

function daysInclusive(from: string, to: string): number | null {
  if (!from || !to) return null;
  const a = new Date(from + "T00:00:00");
  const b = new Date(to + "T00:00:00");
  const diff = Math.round((b.getTime() - a.getTime()) / 86_400_000);
  if (Number.isNaN(diff) || diff < 0) return null;
  return diff + 1;
}

function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`flex min-w-0 flex-col gap-1 ${className}`}>
      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-sm text-slate-800 outline-none focus:border-blue-400 focus:bg-white";
const readOnlyClass =
  "w-full rounded border border-slate-200 bg-slate-50 px-2 py-1.5 text-sm text-slate-700";

export function TravelRequestForm({ onCreated }: { onCreated: () => void }) {
  const { employee } = useAuth();
  const [open, setOpen] = useState(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [visitingPlace, setVisitingPlace] = useState("");
  const [city, setCity] = useState(employee?.city ?? "");
  const [purpose, setPurpose] = useState("");
  const [modeOfTravel, setModeOfTravel] = useState("Flight");
  const [isInternational, setIsInternational] = useState(false);
  const [advance, setAdvance] = useState("0");
  const [lines, setLines] = useState<EstimateDraft[]>(
    DEFAULT_HEADS.map((h) => ({ ...h, estimate: "" })),
  );

  const nights = useMemo(() => {
    const d = daysInclusive(fromDate, toDate);
    return d && d > 1 ? d - 1 : d;
  }, [fromDate, toDate]);

  const dayCount = daysInclusive(fromDate, toDate);
  const estimates = lines.map((l) => Number(l.estimate) || 0);
  const estimatedTotal = estimates.reduce((s, n) => s + n, 0);
  const employeeBorne = lines.reduce(
    (s, l) => s + (l.borne_by === "Employee" ? Number(l.estimate) || 0 : 0),
    0,
  );
  const advanceCap = Math.round(employeeBorne * 0.6 * 100) / 100;
  const advanceNum = Number(advance) || 0;

  const create = useMutation({
    mutationFn: (payload: TravelRequestCreatePayload) => TravelRequestsApi.create(payload),
    onSuccess: () => {
      setOpen(false);
      onCreated();
    },
  });

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded-md border border-dashed border-slate-300 px-4 py-2 text-sm text-slate-500 hover:border-blue-400 hover:text-blue-600"
      >
        + New travel request
      </button>
    );
  }

  const updateLine = (idx: number, patch: Partial<EstimateDraft>) => {
    setLines((prev) => prev.map((row, i) => (i === idx ? { ...row, ...patch } : row)));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate({
      from_date: fromDate,
      to_date: toDate,
      visiting_place: visitingPlace,
      city,
      purpose,
      mode_of_travel: modeOfTravel,
      is_international: isInternational,
      advance_requested: advanceNum,
      estimate_lines: lines
        .filter((l) => l.head.trim() && (Number(l.estimate) || 0) > 0)
        .map((l) => ({
          head: l.head,
          basis:
            l.head === "Lodging" && !l.basis && nights
              ? `${nights} night${nights === 1 ? "" : "s"}`
              : l.basis,
          estimate: Number(l.estimate) || 0,
          borne_by: l.borne_by,
        })),
    });
  };

  return (
    <form
      onSubmit={submit}
      className="w-full max-w-5xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
    >
      <div className="border-b bg-white px-5 py-4">
        <div className="text-lg font-semibold tracking-wide text-slate-900">TRAVEL REQUEST FORM</div>
        <div className="text-xs text-slate-500">
          Nortex Industries Ltd | Form NTX-TRF-02 | Rev Nov 2025
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Travel Request ID">
            <div className={readOnlyClass}>Assigned on create (TRQ-YYYY-nnnn)</div>
          </Field>
          <Field label="Issue date">
            <div className={readOnlyClass}>{new Date().toLocaleDateString("en-IN")}</div>
          </Field>
        </div>
      </div>

      <section className="border-b px-5 py-4">
        <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-600">1) Employee detail</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Employee name">
            <div className={readOnlyClass}>{employee?.name ?? "—"}</div>
          </Field>
          <Field label="Employee code">
            <div className={readOnlyClass}>{employee?.emp_code ?? "—"}</div>
          </Field>
          <Field label="Designation">
            <div className={readOnlyClass}>{employee?.designation ?? "—"}</div>
          </Field>
          <Field label="Department">
            <div className={readOnlyClass}>{employee?.department ?? "—"}</div>
          </Field>
          <Field label="Cost centre">
            <div className={readOnlyClass}>{employee?.cost_centre ?? "—"}</div>
          </Field>
          <Field label="Reporting manager">
            <div className={readOnlyClass}>{employee?.reporting_manager_name ?? "—"}</div>
          </Field>
        </div>
      </section>

      <section className="border-b px-5 py-4">
        <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-600">2) Travel detail</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="From date">
            <input required type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className={inputClass} />
          </Field>
          <Field label="To date">
            <input required type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className={inputClass} />
          </Field>
          <Field label="No. of days">
            <div className={readOnlyClass}>{dayCount ?? "—"}</div>
          </Field>
          <Field label="Travel category">
            <div className={readOnlyClass}>
              {isInternational ? "International" : city ? `Domestic — ${city}` : "Domestic"}
            </div>
          </Field>
          <Field label="Visiting place / company">
            <input
              required
              value={visitingPlace}
              onChange={(e) => setVisitingPlace(e.target.value)}
              placeholder="e.g. Bengaluru / Vertex Technologies"
              className={inputClass}
            />
          </Field>
          <Field label="City (for lodging / meal tier)">
            <input required value={city} onChange={(e) => setCity(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Purpose of travel">
            <input required value={purpose} onChange={(e) => setPurpose(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Mode of travel">
            <select value={modeOfTravel} onChange={(e) => setModeOfTravel(e.target.value)} className={inputClass}>
              <option>Flight</option>
              <option>Rail</option>
              <option>Road</option>
              <option>Other</option>
            </select>
          </Field>
          <Field label="Currency">
            <div className={readOnlyClass}>INR</div>
          </Field>
          <label className="flex items-end gap-2 pb-1 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={isInternational}
              onChange={(e) => setIsInternational(e.target.checked)}
            />
            International travel
          </label>
        </div>
      </section>

      <section className="border-b px-5 py-4">
        <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-600">3) Estimated cost</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-sm">
            <thead>
              <tr className="bg-slate-800 text-left text-[11px] uppercase tracking-wide text-white">
                <th className="px-2 py-2 font-semibold">Head</th>
                <th className="px-2 py-2 font-semibold">Basis</th>
                <th className="px-2 py-2 font-semibold">Estimate</th>
                <th className="px-2 py-2 font-semibold">Borne by</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((row, idx) => (
                <tr key={row.head} className="border-b border-slate-100">
                  <td className="px-2 py-1.5 text-slate-700">{row.head}</td>
                  <td className="px-2 py-1.5">
                    <input
                      value={row.basis}
                      placeholder={
                        row.head === "Lodging" && nights
                          ? `${nights} night${nights === 1 ? "" : "s"}`
                          : undefined
                      }
                      onChange={(e) => updateLine(idx, { basis: e.target.value })}
                      className={inputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      type="number"
                      min={0}
                      step="0.01"
                      value={row.estimate}
                      onChange={(e) => updateLine(idx, { estimate: e.target.value })}
                      className={inputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <select
                      value={row.borne_by}
                      onChange={(e) => updateLine(idx, { borne_by: e.target.value as BorneBy })}
                      className={inputClass}
                    >
                      <option value="Company">Company</option>
                      <option value="Employee">Employee</option>
                    </select>
                  </td>
                </tr>
              ))}
              <tr className="bg-slate-50 font-semibold">
                <td className="px-2 py-2" colSpan={2}>
                  Total estimated cost
                </td>
                <td className="px-2 py-2">{inr(estimatedTotal)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
        <div className="mt-4 grid max-w-sm grid-cols-1 gap-2">
          <Field label="Travel advance requested">
            <input
              type="number"
              min={0}
              step="0.01"
              value={advance}
              onChange={(e) => setAdvance(e.target.value)}
              className={inputClass}
            />
          </Field>
          <p className="text-xs text-slate-500">
            Policy 1.2: at most 60% of the employee-borne estimate ({inr(advanceCap)} of {inr(employeeBorne)}).
            Company-booked heads do not increase what can be drawn.
          </p>
        </div>
      </section>

      <section className="border-b px-5 py-4">
        <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-600">4) Approval workflow</h3>
        <p className="mb-2 text-xs text-slate-500">
          Levels required depend on amount and travel category — see expense_policy.md. Filled in when the
          claim is submitted, not on this request.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-sm">
            <thead>
              <tr className="bg-slate-800 text-left text-[11px] uppercase tracking-wide text-white">
                <th className="px-2 py-2">Level</th>
                <th className="px-2 py-2">Role</th>
                <th className="px-2 py-2">Name</th>
                <th className="px-2 py-2">Decision</th>
                <th className="px-2 py-2">Date</th>
                <th className="px-2 py-2">Remarks</th>
              </tr>
            </thead>
            <tbody>
              {APPROVAL_ROWS.map((row) => (
                <tr key={row.level} className="border-b border-slate-100">
                  <td className="px-2 py-2 text-slate-600">{row.level}</td>
                  <td className="px-2 py-2 text-slate-800">{row.role}</td>
                  <td className="px-2 py-2 text-slate-300">—</td>
                  <td className="px-2 py-2 text-slate-300">—</td>
                  <td className="px-2 py-2 text-slate-300">—</td>
                  <td className="px-2 py-2 text-slate-300">—</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="bg-slate-50 px-5 py-3 text-[11px] leading-relaxed text-slate-500">
        <div className="font-semibold uppercase tracking-wide text-slate-600">Legend</div>
        Amber cells are the ones you fill in. Everything else is fixed form structure. Total estimated cost is
        a sum — do not type a number over it. Approval levels required depend on amount and travel category.
      </div>

      {create.isError && (
        <p className="px-5 pt-3 text-sm text-red-600">
          {(create.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
            "Could not create travel request"}
        </p>
      )}

      <div className="flex gap-2 px-5 py-4">
        <button
          type="submit"
          disabled={create.isPending}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {create.isPending ? "Creating…" : "Create"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded px-4 py-1.5 text-sm text-slate-500">
          Cancel
        </button>
      </div>
    </form>
  );
}
