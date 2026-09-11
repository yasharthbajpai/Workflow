from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_employee
from app.database import get_db
from app.models import Employee
from app.schemas.auth import EmployeeOut

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeOut])
def list_employees(_: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Employee).options(selectinload(Employee.reporting_manager)).order_by(Employee.emp_code)
    ).all()
    return [EmployeeOut.model_validate(e) for e in rows]
