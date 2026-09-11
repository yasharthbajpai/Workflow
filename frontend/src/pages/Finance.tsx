import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FinanceApi } from "../api/endpoints";
import { ClaimReviewPanel } from "../components/ClaimReviewPanel";
import { inr } from "../lib/format";
import type { Claim } from "../types";

function TotalsStrip({ claim }: { claim: Claim }) {
  return (
    <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
      <div>
        <div className="text-[11px] text-slate-400">Employee-paid</div>
        <div className="font-medium">{inr(claim.total_employee_paid)}</div>
      </div>
      <div>
        <div className="text-[11px] text-slate-400">Company-paid (memo)</div>
        <div className="font-medium">{inr(claim.total_company_paid)}</div>
      </div>
      <div>
        <div className="text-[11px] text-slate-400">Disallowed</div>
        <div className="font-medium text-red-600">{inr(claim.total_disallowed)}</div>
      </div>
      <div>
        <div className="text-[11px] text-slate-400">Advance drawn</div>
        <div className="font-medium">{inr(claim.advance_drawn)}</div>
      </div>
      <div>
        <div className="text-[11px] text-slate-400">Net reimbursable</div>
        <div className="font-semibold">{inr(claim.net_reimbursable)}</div>
      </div>
      <div>
        <div className="text-[11px] text-slate-400">Payable</div>
        <div className="font-semibold text-emerald-700">{inr(claim.amount_payable)}</div>
      </div>
      <div>
        <div className="text-[11px] text-slate-400">Recoverable</div>
        <div className="font-semibold text-red-600">{inr(claim.amount_recoverable)}</div>
      </div>
    </div>
  );
}

function VerifyCard({ claim }: { claim: Claim }) {
  const qc = useQueryClient();
  const verify = useMutation({
    mutationFn: () => FinanceApi.verify(claim.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance-verification-queue"] });
      qc.invalidateQueries({ queryKey: ["finance-payment-run"] });
      qc.invalidateQueries({ queryKey: ["dashboard-summary"] });
      qc.invalidateQueries({ queryKey: ["claim", claim.id] });
    },
  });

  return (
    <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
      <div className="border-b bg-slate-50 px-5 py-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Awaiting finance verification</div>
        <TotalsStrip claim={claim} />
      </div>
      <div className="px-5 py-4">
        <ClaimReviewPanel claimId={claim.id} summary={claim} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-blue-50 px-5 py-3">
        <p className="text-xs text-slate-600">
          Policy 2.1 — Finance verifies every claim after business approvals, regardless of value.
        </p>
        <button
          onClick={() => verify.mutate()}
          disabled={verify.isPending}
          className="rounded bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {verify.isPending ? "Verifying…" : "Verify claim"}
        </button>
      </div>
      {verify.isError && <p className="px-5 pb-3 text-xs text-red-600">Verification failed — refresh and try again.</p>}
    </div>
  );
}

function PayCard({ claim }: { claim: Claim }) {
  const qc = useQueryClient();
  const [reference, setReference] = useState(`PAY/2026/${String(claim.id).padStart(4, "0")}`);
  const pay = useMutation({
    mutationFn: () => FinanceApi.pay(claim.id, reference),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance-payment-run"] });
      qc.invalidateQueries({ queryKey: ["dashboard-summary"] });
      qc.invalidateQueries({ queryKey: ["claim", claim.id] });
    },
  });

  return (
    <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
      <div className="border-b bg-emerald-50 px-5 py-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Verified — ready for payment run</div>
        <TotalsStrip claim={claim} />
      </div>
      <div className="px-5 py-4">
        <ClaimReviewPanel claimId={claim.id} summary={claim} />
      </div>
      <div className="flex flex-wrap items-end justify-between gap-3 border-t bg-slate-50 px-5 py-3">
        <label className="text-xs text-slate-600">
          Payment reference
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            className="mt-1 block w-56 rounded border bg-white px-2 py-1.5 text-sm"
          />
        </label>
        <button
          onClick={() => pay.mutate()}
          disabled={pay.isPending || !reference.trim()}
          className="rounded bg-emerald-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {pay.isPending ? "Releasing…" : "Release payment"}
        </button>
      </div>
      {pay.isError && <p className="px-5 pb-3 text-xs text-red-600">Payment failed — refresh and try again.</p>}
    </div>
  );
}

export function FinancePage() {
  const { data: verifyQueue } = useQuery({
    queryKey: ["finance-verification-queue"],
    queryFn: FinanceApi.verificationQueue,
  });
  const { data: paymentRun } = useQuery({ queryKey: ["finance-payment-run"], queryFn: FinanceApi.paymentRun });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-lg font-bold text-slate-800">Finance</h1>
        <p className="text-sm text-slate-500">
          Review the full settlement — every line, flag, and advance — then verify (policy 2.1) and pay on the
          10th or 25th run (policy 5.4).
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Verification queue</h2>
        {verifyQueue?.length === 0 && (
          <div className="rounded-xl border bg-white p-6 text-center text-sm text-slate-400">Nothing to verify.</div>
        )}
        {verifyQueue?.map((c) => (
          <VerifyCard key={c.id} claim={c} />
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Payment run (verified, awaiting payment)</h2>
        {paymentRun?.length === 0 && (
          <div className="rounded-xl border bg-white p-6 text-center text-sm text-slate-400">
            Nothing scheduled for payment.
          </div>
        )}
        {paymentRun?.map((c) => (
          <PayCard key={c.id} claim={c} />
        ))}
      </section>
    </div>
  );
}
