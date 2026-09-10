# Demo walkthrough (3–5 minutes)

Assumes the backend is seeded (`alembic upgrade head && python -m app.seed`)
and both servers are running. If demoing the deployed version, hit the
backend's `/health` once first to warm it out of Render's free-tier cold
start.

## 1. Log in as the employee (0:00)

`http://localhost:5173/login` → pick **Chaitanya Reddy** from the demo list
(password `Nortex@123`). Point out the dashboard: a stage bar chart (currently
empty) and "My claims" (currently empty) — nothing has been submitted yet.

## 2. Scan the inbox (0:30)

Go to **Submit**. There's one travel request already seeded, `TRQ-2026-0001`
— Chaitanya's Bengaluru trip. Click **"Scan my inbox with AI"**.

Wait for the extracted lines table. Narrate the traps as they appear:

- **Three INR 172 Uber lines become one.** One is greyed out and flagged
  `PAYMENT_FAILED` (INFO), the payment failure never went through. Another
  is greyed out and flagged `DUPLICATE_BILL` (policy 5.3) — same merchant,
  date, amount and route as the line above it, which is the one that
  actually counts.
- **Deepa Nair's INR 640 cab is excluded.** Flagged `THIRD_PARTY_EXPENSE`
  (BLOCK, policy 4) and greyed out — it's on the claim for transparency, but
  excluded from every total.
- **Both flight sectors show `paid_by: Company`.** Flagged
  `COMPANY_PAID_NOT_CLAIMABLE` (INFO, policy 3.2) — booked on the corporate
  card, recorded for audit, never reimbursed.
- **The hotel line's tax is apportioned.** Point at `tax_amount: 2070.00` —
  not the invoice's full CGST+SGST of 2,304, because that also covered
  laundry, mini bar and in-room dining. Laundry and mini bar appear as their
  own fully-disallowed lines citing policy 4; in-room dining is its own line,
  treated as a meal (see the delivery note's assumption on this).
- **The Spice Terrace dinner is blocked.** Flagged `BE_MISSING_ATTENDEES`
  (BLOCK, policy 3.5) — INR 2,255 is over the entertainment threshold and the
  email never named the four attendees. The **Submit** button is disabled
  while this is outstanding.

## 3. Fix the block and submit (2:00)

On the dinner line, fill in attendee names and the organisation (e.g.
"Vertex procurement team" → four names + "Vertex Technologies") and save.
The BLOCK flag clears, the line becomes reimbursable, the Submit button
enables. Click **Submit claim for approval**.

## 4. Approve chain (2:30)

Log out, log in as **Suresh Iyer** (Chaitanya's Reporting Manager).
**Approvals** shows exactly this one claim — nothing else, because the queue
only ever shows what's awaiting *that* person. Approve it.

Log in as **Meera Krishnan** (Head of Department) — the claim is now in her
queue (Suresh, being the claimant's manager, was level 1; Meera is level 2).
Approve it.

## 5. Finance verify + pay (3:15)

Log in as **Ravi Menon** (Finance). **Finance → Verification queue** shows
the claim regardless of its value (policy 2.1 — Finance verifies every
claim). Verify it, then find it under **Payment run** and release payment
with a reference number.

Open the claim detail page at any point in this sequence to show the
`<ApprovalProgress>` stepper filling in left to right, and the event
timeline underneath recording every action.

## 6. Bonus: show a return/resubmit cycle (if time remains)

Scan a fresh travel request, submit it, then as the approver click
**Return with remarks** instead of approving. Log back in as the employee —
the claim is `RETURNED`, editable, still against the same Travel Request ID.
Fix it and click **Resubmit** — the stepper resets to level 1 and a note
appears: "Resubmission #2 — a prior cycle was returned for correction."
