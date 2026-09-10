# Delivery note

## What I understood the problem to be

The pack is a specification disguised as an inbox. The real ask isn't "read
some emails" — it's "correctly resolve the traps a real inbox contains, and
route the result through the approval chain the policy actually describes,"
because that's what makes the 25-minute manual form-filling (and the
follow-up calls to Finance) go away. The graded traps I found and handled:

- Uber's 17 Jun INR 172 cab arrives three times (payment-failure notice, the
  real receipt, a forwarded resend) — one expense, two duplicates.
- Deepa Nair's forwarded INR 640 Chennai cab belongs to a different employee's
  trip entirely.
- The hotel folio charges CGST+SGST on a subtotal that includes laundry,
  mini bar and in-room dining — only the room-tariff's share of that tax
  (INR 2,070, not the full INR 2,304) is reimbursable.
- Both flight sectors were on the corporate card — employees don't claim
  flights (policy 3.2); they're recorded as company-paid memo lines.
- The INR 2,255 dinner is Business Entertainment (above the INR 2,000
  threshold) but the email never names attendees — this has to block
  submission, not pass silently.
- A promotional email and the approval/advance threads are noise, not claims.

## What I built

- **Backend** (FastAPI + SQLAlchemy + Postgres, `Sample_test` schema, Alembic
  migrations): access control seeded from `employee_master.csv`; policy
  numbers (lodging/meal caps, thresholds, bands) seeded from
  `expense_policy.md` as data, not constants.
- **Gemini extracts, Python decides**: `gemini-3.6-flash` (multimodal, reads
  the two receipt PNGs directly) turns each document into a structured
  candidate; a deterministic policy engine in `app/services/policy_engine.py`
  owns every rupee and every compliance verdict — tax apportionment, tariff
  caps, dedupe, business-entertainment gating, meal caps. No money figure
  ever depends on a model response.
- **Routing** (`app/services/routing.py`): Finance is appended unconditionally
  as the terminal step on every claim (2.1). Business levels are resolved by
  walking the `reporting_manager_code` chain one step per required level,
  never revisiting the claimant or anyone already assigned to an earlier
  level (2.2) — verified against the Suresh Iyer case where his manager and
  his manager's manager would otherwise collide.
- **Return/resubmit** (2.3): a returned claim stays against the same Travel
  Request ID, is editable, and resubmission restarts approval at level 1 —
  history from the earlier cycle is kept, not overwritten.
- **Frontend** (React + Vite + TS): a Submit flow (scan → review flagged
  lines → fix → submit) separate from an Approve flow (queue of only what's
  awaiting me, with Approve / Reject / Return-with-remarks), a Finance screen
  for verification + the payment run, and a shared `<ApprovalProgress>`
  stepper on every claim plus a dashboard bar chart of claims by stage.

## Assumptions I made and would flag to a reviewer

- **In-room dining is a meal, not "in-room entertainment."** Policy 4 bars
  the latter; I read the former as room service and capped it under the
  daily meal limit instead of auto-disallowing it. Flagged `INFO` on the
  line either way, since it's a judgement call.
- **Resubmission restarts approval at level 1**, even though only one level
  returned the claim. An edit can move the claimed amount into a different
  band, so I didn't try to resume mid-chain.
- **The claimed value, not the estimate, drives the approval band** — the
  policy 2 table header says "Estimated / claimed value," and a settlement
  claim's claimed value is what's actually being approved.
- **Meal-cap overage, when several meal lines land on the same day, is
  allocated to whichever line was extracted last.** A reasonable
  simplification; real folios rarely split this finely.
- **All 9 employees share one demo password** rather than a real onboarding
  flow — this is a demo of the workflow, not of identity management.

## What I deliberately left out

- Real mailbox OAuth (Gmail/Outlook) — documents are seeded from the pack
  instead of pulled live.
- File storage on S3 — receipt bytes live in Postgres (`document.image_bytes`),
  fine at this scale, not fine at production volume.
- Email notifications on every approval step.
- A UI for editing the Travel Request approval chain itself (email threads
  01/02 are seeded as historical context, not re-litigated in the app).

## Where it breaks

- **No Gemini API key**: "Scan my inbox" falls back to a small regex parser
  for Uber/MakeMyTrip sender patterns only. It resolves the duplicate-cab and
  flight-memo traps, but can't itemise the hotel folio or read the dinner
  bill image — those need the model. Set `GEMINI_API_KEY` to see the full
  pipeline.
- **Gemini extraction accuracy** on receipts outside this exact pack's format
  isn't tested — a genuinely novel merchant layout could mis-extract or land
  in the generic `OTHER` bucket with `needs_review=true`, which is the
  intended safety valve but not a substitute for a human check.
- **Amounts use `float`/`round()`, not fixed-point Decimal arithmetic** end to
  end — fine for a demo, not for an audited ledger.
- **Render's free tier spins down** when idle; the first request after a
  while takes about a minute.
- **RBAC on claim visibility is coarse**: any approver-capable role can view
  any claim for audit purposes, rather than scoping strictly to "my direct
  reports."

## Assumption call I want to flag explicitly (per the take-home's ask)

The reporting-chain walk in `resolve_approval_chain` never had to prove the
"skip" case *against this specific org chart* — Suresh Iyer's chain (Suresh →
Meera → Arvind → Nandita) already has one distinct person per level, so a
plain upward walk resolves it correctly by construction. I still wrote the
resolver to detect and skip past a person already used (self or an earlier
level) for the general case, and unit-tested it in
`scripts/smoke_test_workflow.py`; it just doesn't get visibly exercised by
this pack's specific data. I'd rather say that plainly than imply the demo
proves something it doesn't.
