import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { FinanceApi } from "../api/endpoints";
import { inr } from "../lib/format";
import type { Claim } from "../types";

function VerifyRow({ claim }: { claim: Claim }) {
  const qc = useQueryClient();
  const verify = useMutation({
    mutationFn: () => FinanceApi.verify(claim.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance-verification-queue"] });
      qc.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });
  return (
    <div className="flex items-center justify-between rounded-xl border bg-white p-4 shadow-sm">
      <div>
        <Link to={`/claims/${claim.id}`} className="font-semibold text-slate-800 hover:underline">
          {claim.travel_request_no}
        </Link>
        <div className="text-xs text-slate-400">{claim.employee_name}</div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="text-xs text-slate-400">Net reimbursable</div>
          <div className="font-semibold">{inr(claim.net_reimbursable)}</div>
        </div>
        <button
          onClick={() => verify.mutate()}
          disabled={verify.isPending}
          className="rounded bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
        >
          Verify
        </button>
      </div>
    </div>
  );
}

function PayRow({ claim }: { claim: Claim }) {
  const qc = useQueryClient();
  const [reference, setReference] = useState(`PAY/2026/${String(claim.id).padStart(4, "0")}`);
  const pay = useMutation({
    mutationFn: () => FinanceApi.pay(claim.id, reference),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance-payment-run"] });
      qc.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });
  return (
    <div className="flex items-center justify-between rounded-xl border bg-white p-4 shadow-sm">
      <div>
        <Link to={`/claims/${claim.id}`} className="font-semibold text-slate-800 hover:underline">
          {claim.travel_request_no}
        </Link>
        <div className="text-xs text-slate-400">{claim.employee_name}</div>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-right">
          <div className="text-xs text-slate-400">Payable</div>
          <div className="font-semibold text-emerald-700">{inr(claim.amount_payable)}</div>
        </div>
        <input
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          className="w-40 rounded border px-2 py-1.5 text-xs"
        />
        <button
          onClick={() => pay.mutate()}
          disabled={pay.isPending}
          className="rounded bg-emerald-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
        >
          Release payment
        </button>
      </div>
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
          Every claim is verified by Finance regardless of value (policy 2.1), then paid in the run on the 10th or
          25th (policy 5.4).
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Verification queue</h2>
        {verifyQueue?.length === 0 && (
          <div className="rounded-xl border bg-white p-6 text-center text-sm text-slate-400">Nothing to verify.</div>
        )}
        {verifyQueue?.map((c) => <VerifyRow key={c.id} claim={c} />)}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Payment run (verified, awaiting payment)</h2>
        {paymentRun?.length === 0 && (
          <div className="rounded-xl border bg-white p-6 text-center text-sm text-slate-400">
            Nothing scheduled for payment.
          </div>
        )}
        {paymentRun?.map((c) => <PayRow key={c.id} claim={c} />)}
      </section>
    </div>
  );
}
