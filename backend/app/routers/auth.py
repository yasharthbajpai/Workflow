"""Login + who-am-I + a demo-credentials listing endpoint.

All 9 seeded employees share settings.demo_password (Nortex@123 by default),
which /auth/demo-users surfaces so the login screen can list every account
without hardcoding the password twice.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_employee
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models import Employee
from app.schemas.auth import EmployeeOut, LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    employee = db.scalar(select(Employee).where(Employee.email == payload.email.lower().strip()))
    if not employee or not verify_password(payload.password, employee.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(subject=employee.emp_code, extra_claims={"role": employee.role_code})
    return LoginResponse(access_token=token, employee=EmployeeOut.model_validate(employee))


@router.get("/me", response_model=EmployeeOut)
def me(employee: Employee = Depends(get_current_employee)) -> EmployeeOut:
    return EmployeeOut.model_validate(employee)


@router.get("/demo-users", response_model=list[EmployeeOut])
def demo_users(db: Session = Depends(get_db)) -> list[EmployeeOut]:
    """Unauthenticated listing so the login screen can show every seeded
    account. The shared demo password is never stored — only the plaintext
    default from settings, surfaced once here for the demo login screen.
    """
    employees = db.scalars(select(Employee).order_by(Employee.emp_code)).all()
    return [EmployeeOut.model_validate(e) for e in employees]
