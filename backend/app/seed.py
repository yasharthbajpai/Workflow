"""Idempotent seeder.

Run with `python -m app.seed`. Populates:
  - app_role / permission / role_permission (RBAC)
  - employee, from employee_master.csv, all with the same demo password
  - city_tier, policy_config, approval_band, from expense_policy.md
  - document rows for every file in sample_emails/ and receipts/, parsed but
    NOT yet run through the extraction/policy engine (that happens through
    the "Scan my inbox" action so it is demonstrably a live, on-demand step)
  - one seed TravelRequest + Advance for Chaitanya Reddy's Bengaluru trip,
    matching emails 01-03, so the demo has something to submit against on
    first login without any manual data entry

Safe to re-run: every insert is guarded by an existence check.
"""
from __future__ import annotations

import csv
import email
import mimetypes
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal, ensure_schema
from app.models import (
    Advance,
    AppRole,
    ApprovalBand,
    CityTier,
    Document,
    Employee,
    EstimateLine,
    Permission,
    PolicyConfig,
    TravelRequest,
    role_permission,
)
from app.models.enums import TravelRequestStatus

# backend/app/seed.py -> parents[2] == the pack/ root, where sample_emails/,
# receipts/ and employee_master.csv live alongside backend/ and frontend/.
PACK_DIR = Path(__file__).resolve().parents[2]
EMAILS_DIR = PACK_DIR / "sample_emails"
RECEIPTS_DIR = PACK_DIR / "receipts"
EMPLOYEE_CSV = PACK_DIR / "employee_master.csv"

# employee_master.csv role string -> app_role.code
ROLE_CODE_BY_CSV_LABEL = {
    "Employee": "EMPLOYEE",
    "Reporting Manager": "REPORTING_MANAGER",
    "Head of Department": "HOD",
    "Head of Division": "HOD_DIVISION",
    "MD": "MD",
    "Finance": "FINANCE",
}

ROLES = [
    # code, name, approval_level (None = not part of the RM->HoD->HoDiv->MD chain)
    ("EMPLOYEE", "Employee", None),
    ("REPORTING_MANAGER", "Reporting Manager", 1),
    ("HOD", "Head of Department", 2),
    ("HOD_DIVISION", "Head of Division", 3),
    ("MD", "MD / CEO", 4),
    ("FINANCE", "Finance", None),
]

PERMISSIONS = [
    ("claim.create", "Create and submit a travel expense claim"),
    ("claim.view_own", "View own claims"),
    ("claim.view_reports", "View claims of reporting employees"),
    ("claim.approve", "Approve / reject / return a claim at a business level"),
    ("claim.finance_verify", "Verify a claim and release payment"),
    ("travel_request.create", "Create a travel request"),
    ("travel_request.approve", "Approve a travel request"),
]

ROLE_PERMISSIONS = {
    "EMPLOYEE": ["claim.create", "claim.view_own", "travel_request.create"],
    "REPORTING_MANAGER": [
        "claim.create",
        "claim.view_own",
        "claim.view_reports",
        "claim.approve",
        "travel_request.create",
        "travel_request.approve",
    ],
    "HOD": ["claim.create", "claim.view_own", "claim.view_reports", "claim.approve", "travel_request.approve"],
    "HOD_DIVISION": [
        "claim.create",
        "claim.view_own",
        "claim.view_reports",
        "claim.approve",
        "travel_request.approve",
    ],
    "MD": ["claim.create", "claim.view_own", "claim.view_reports", "claim.approve", "travel_request.approve"],
    "FINANCE": ["claim.view_reports", "claim.finance_verify"],
}

# Policy 3.1 — Tier 1 cities named explicitly in the policy. Anything else
# falls back to Tier 3 at lookup time unless added here as Tier 2.
CITY_TIERS = [
    ("Bengaluru", 1),
    ("Bangalore", 1),
    ("Mumbai", 1),
    ("Delhi NCR", 1),
    ("Delhi", 1),
    ("New Delhi", 1),
    ("Hyderabad", 1),
    ("Chennai", 1),
    ("Pune", 1),
    ("Kolkata", 1),
]

POLICY_CONFIG = [
    ("LODGING_CAP_TIER_1", "6000", "Policy 3.1 — Tier 1 room tariff limit per night, excl. taxes"),
    ("LODGING_CAP_TIER_2", "4000", "Policy 3.1 — Tier 2 room tariff limit per night, excl. taxes"),
    ("LODGING_CAP_TIER_3", "2800", "Policy 3.1 — Tier 3+ room tariff limit per night, excl. taxes"),
    ("MEAL_CAP_TIER_1", "1500", "Policy 3.3 — Tier 1 meal cap per full day"),
    ("MEAL_CAP_TIER_2_3", "1000", "Policy 3.3 — Tier 2/3 meal cap per full day"),
    ("MEAL_BILL_REQUIRED_ABOVE", "500", "Policy 3.3 — bills required for meal claims above this amount"),
    ("BUSINESS_ENTERTAINMENT_APPROVAL_THRESHOLD", "2000", "Policy 3.5 — prior HoD approval required above this"),
    ("SUBMISSION_WINDOW_DAYS", "7", "Policy 5.1 — claim must be submitted within N calendar days of return"),
    ("ADVANCE_MAX_PCT_OF_ESTIMATE", "60", "Policy 1.2 — max advance as % of estimated employee-borne cost"),
    ("PAYMENT_RUN_DAY_1", "10", "Policy 5.4"),
    ("PAYMENT_RUN_DAY_2", "25", "Policy 5.4"),
    ("FINANCE_VERIFIER_EMP_CODE", "NX-3305", "Employee who acts as the Finance verification step"),
]

# Policy 2 approval matrix. FINANCE is deliberately absent — appended
# unconditionally by the routing engine per policy 2.1, never part of a band.
APPROVAL_BANDS = [
    dict(
        code="BAND_1",
        min_amount=0,
        max_amount=25000,
        international_only=False,
        required_levels=["REPORTING_MANAGER"],
        description="Up to INR 25,000: Reporting Manager",
    ),
    dict(
        code="BAND_2",
        min_amount=25000.01,
        max_amount=75000,
        international_only=False,
        required_levels=["REPORTING_MANAGER", "HOD"],
        description="INR 25,001-75,000: Reporting Manager, Head of Department",
    ),
    dict(
        code="BAND_3",
        min_amount=75000.01,
        max_amount=200000,
        international_only=False,
        required_levels=["REPORTING_MANAGER", "HOD", "HOD_DIVISION"],
        description="INR 75,001-2,00,000: RM, HoD, Head of Division",
    ),
    dict(
        code="BAND_4",
        min_amount=200000.01,
        max_amount=None,
        international_only=False,
        required_levels=["REPORTING_MANAGER", "HOD", "HOD_DIVISION", "MD"],
        description="Above INR 2,00,000: RM, HoD, Head of Division, MD/CEO",
    ),
    dict(
        code="BAND_INTL",
        min_amount=0,
        max_amount=None,
        international_only=True,
        required_levels=["REPORTING_MANAGER", "HOD", "HOD_DIVISION", "MD"],
        description="Any international travel: RM, HoD, Head of Division, MD/CEO",
    ),
]


def _get_or_create(db: Session, model, pk_field: str, pk_value, **kwargs):
    existing = db.get(model, pk_value)
    if existing:
        return existing, False
    obj = model(**{pk_field: pk_value}, **kwargs)
    db.add(obj)
    return obj, True


def seed_roles_and_permissions(db: Session) -> None:
    for code, name, level in ROLES:
        _get_or_create(db, AppRole, "code", code, name=name, approval_level=level)
    db.flush()

    for code, description in PERMISSIONS:
        _get_or_create(db, Permission, "code", code, description=description)
    db.flush()

    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        role = db.get(AppRole, role_code)
        existing_codes = {p.code for p in role.permissions}
        for perm_code in perm_codes:
            if perm_code not in existing_codes:
                role.permissions.append(db.get(Permission, perm_code))


def seed_employees(db: Session) -> None:
    demo_hash = hash_password(settings.demo_password)
    with EMPLOYEE_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Two passes: employees can reference a reporting_manager_code that is
    # defined later in the file (not the case here, but keep it robust).
    for row in rows:
        _get_or_create(
            db,
            Employee,
            "emp_code",
            row["emp_code"],
            name=row["name"],
            email=row["email"],
            designation=row["designation"],
            department=row["department"],
            cost_centre=row["cost_centre"],
            city=row["city"],
            reporting_manager_code=row["reporting_manager_code"] or None,
            role_code=ROLE_CODE_BY_CSV_LABEL[row["role"]],
            password_hash=demo_hash,
        )
    db.flush()


def seed_policy_data(db: Session) -> None:
    for city, tier in CITY_TIERS:
        _get_or_create(db, CityTier, "city", city, tier=tier)

    for key, value, description in POLICY_CONFIG:
        _get_or_create(db, PolicyConfig, "key", key, value=value, description=description)

    for band in APPROVAL_BANDS:
        code = band.pop("code")
        _get_or_create(db, ApprovalBand, "code", code, **band)
        band["code"] = code  # restore for idempotent re-run
    db.flush()


# --- Document seeding from the raw pack -------------------------------------

_AMOUNT_RE = re.compile(r"(\d[\d,]*\.\d{2})")


def _parse_eml(path: Path) -> email.message.Message:
    with path.open("rb") as f:
        return email.message_from_binary_file(f)


def _received_at(msg: email.message.Message) -> datetime | None:
    date_hdr = msg.get("Date")
    if not date_hdr:
        return None
    try:
        return parsedate_to_datetime(date_hdr)
    except (TypeError, ValueError):
        return None


def _plain_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                parts.append(payload.decode("utf-8", errors="ignore"))
        return "\n".join(parts)
    payload = msg.get_payload(decode=True) or b""
    return payload.decode("utf-8", errors="ignore")


def seed_documents(db: Session, employee_code: str, travel_request_id: int | None) -> None:
    if db.query(Document).filter(Document.employee_code == employee_code).count() > 0:
        return  # already seeded for this employee

    if EMAILS_DIR.exists():
        for path in sorted(EMAILS_DIR.glob("*.eml")):
            msg = _parse_eml(path)
            doc = Document(
                employee_code=employee_code,
                travel_request_id=travel_request_id,
                filename=path.name,
                mime_type="message/rfc822",
                sender=msg.get("From"),
                subject=msg.get("Subject"),
                received_at=_received_at(msg),
                raw_text=_plain_text(msg),
            )
            db.add(doc)

    if RECEIPTS_DIR.exists():
        for path in sorted(RECEIPTS_DIR.glob("*.png")):
            mime_type, _ = mimetypes.guess_type(str(path))
            doc = Document(
                employee_code=employee_code,
                travel_request_id=travel_request_id,
                filename=path.name,
                mime_type=mime_type or "image/png",
                sender=None,
                subject=path.stem.replace("_", " "),
                received_at=None,
                image_bytes=path.read_bytes(),
            )
            db.add(doc)
    db.flush()


def seed_chaitanya_trip(db: Session) -> TravelRequest | None:
    """One seed Travel Request + Advance matching sample_emails 01-03, so the
    demo has a live trip to scan an inbox and submit a claim against without
    any manual setup.
    """
    existing = db.query(TravelRequest).filter(TravelRequest.travel_request_no == "TRQ-2026-0001").first()
    if existing:
        return existing

    employee_code = "NX-4471"  # Chaitanya Reddy
    if not db.get(Employee, employee_code):
        return None

    tr = TravelRequest(
        travel_request_no="TRQ-2026-0001",
        employee_code=employee_code,
        from_date=date(2026, 6, 16),
        to_date=date(2026, 6, 20),
        visiting_place="Bengaluru / Vertex Technologies",
        city="Bengaluru",
        purpose="Customer meeting + site visit",
        mode_of_travel="Flight",
        is_international=False,
        estimated_total=48000,
        advance_requested=20000,
        status=TravelRequestStatus.APPROVED,
    )
    db.add(tr)
    db.flush()

    db.add_all(
        [
            EstimateLine(travel_request_id=tr.id, head="Air / Rail", basis="Return, economy", estimate=10500, borne_by="Company"),
            EstimateLine(travel_request_id=tr.id, head="Lodging", basis="4 nights", estimate=23000, borne_by="Company"),
            EstimateLine(travel_request_id=tr.id, head="Local conveyance", basis="Actuals", estimate=4000, borne_by="Employee"),
            EstimateLine(travel_request_id=tr.id, head="Meals / allowance", basis="As per policy", estimate=6000, borne_by="Employee"),
        ]
    )
    db.add(Advance(travel_request_id=tr.id, reference="ADV/2026/0619", amount=20000))
    db.flush()
    return tr


def run(db: Session | None = None) -> None:
    """Seeds roles/permissions/employees/policy-data/the demo trip/documents.

    Called with no args for the real app (against settings.db_schema, owns
    and closes its own session). Also called by the standalone smoke-test
    scripts with an explicit `db` bound to an isolated schema (see
    scripts/_smoke_db.py) so they can seed a throwaway copy of this same
    data without touching the shared database the running app/demo uses.
    """
    owns_session = db is None
    if owns_session:
        ensure_schema()
        db = SessionLocal()
    try:
        seed_roles_and_permissions(db)
        seed_employees(db)
        seed_policy_data(db)
        db.commit()

        tr = seed_chaitanya_trip(db)
        db.commit()

        seed_documents(db, "NX-4471", tr.id if tr else None)
        db.commit()
        print("Seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    run()
