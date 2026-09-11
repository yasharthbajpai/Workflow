# Nortex Travel & Expense

A working replacement for Nortex's manual Travel Expense Settlement Form: an
employee's inbox goes in, a policy-checked, approval-routed claim comes out.

- **Backend**: FastAPI + SQLAlchemy + Postgres (`backend/`), deployed on Render
- **Frontend**: React + Vite + TypeScript (`frontend/`), deployed on Vercel
- **AI extraction**: AWS Bedrock (any tool-use-capable model via `BEDROCK_MODEL_ID`,
  e.g. an Anthropic Claude model, called with `boto3`'s Converse API), with a
  regex fallback for the three known senders in the pack so a demo never hard-fails
  on a throttling error or missing credentials

See [`DELIVERY_NOTE.md`](DELIVERY_NOTE.md) for what this is, the assumptions made,
and where it breaks.

## Run it locally

Prerequisites: Python 3.11+, Node 18+, a Postgres instance (local or remote).

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set DATABASE_URL to your Postgres instance, and (optionally)
# AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION / BEDROCK_MODEL_ID

alembic upgrade head   # creates the "Sample_test" schema and every table
python -m app.seed     # loads employee_master.csv, expense_policy.md config, and
                        # the sample_emails/ + receipts/ pack as seed documents

uvicorn app.main:app --reload --port 8000
```

Without `BEDROCK_MODEL_ID` set (or if the credentials are missing/invalid), "Scan my
inbox" falls back to a small regex parser for Uber/MakeMyTrip senders — enough to
demo the duplicate-cab and flight-memo traps, but not the itemised hotel folio or
the dinner bill (those need the model to read the image / itemise the invoice). Set
the four AWS env vars to see the full pipeline.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000 for local dev
npm run dev
```

Open http://localhost:5173 and sign in as any seeded employee — the login screen
lists every account. Every demo account shares the password `Nortex@123`.

### 3. Verify the policy engine and workflow independently

Two standalone scripts exercise the core logic against the real pack data,
without needing the API or a browser:

```bash
cd backend
.venv/bin/python -m scripts.smoke_test_policy_engine   # every trap in the inbox
.venv/bin/python -m scripts.smoke_test_workflow        # 2.2 routing + 2.3 return/resubmit
```

## Deploy

- **Backend → Render**: `render.yaml` at the repo root defines the service
  (`rootDir: backend`, `bash render_start.sh` runs migrations + seed + serve).
  Set `DATABASE_URL` (from a Render Postgres instance), `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `BEDROCK_MODEL_ID`, and `CORS_ORIGINS`
  (your Vercel URL) in the Render dashboard.
- **Frontend → Vercel**: import `frontend/` as the project root, set
  `VITE_API_BASE_URL` to your Render backend URL. `vercel.json` handles the
  SPA rewrite for client-side routing.

Render's free tier spins down when idle — the first request after a while
takes about a minute to wake up.

## Repo layout

```
backend/
  app/
    models/        SQLAlchemy models (access control, policy-as-data, domain)
    schemas/        Pydantic request/response + the extraction schema
    services/       policy_engine, routing, workflow, bedrock_extraction, claim_builder
    routers/        FastAPI routers
    seed.py          idempotent seed from employee_master.csv + expense_policy.md + the pack
  alembic/           migrations
  scripts/           standalone verification scripts (see above)
frontend/
  src/
    pages/           Dashboard, Submit, Approvals, Finance, ClaimDetail, Login
    components/      ApprovalProgress (per-claim stepper), StageBarChart, ClaimLinesTable
    api/             axios client + typed endpoint wrappers
render.yaml
```
