"""FastAPI dependencies: current-user resolution and permission gating.

get_current_employee reads the bearer token, decodes it, and loads the
Employee row fresh from the DB (never trusts stale claims about role for
authorization decisions — only the emp_code in the token is trusted).
require_permission(...) then checks that employee's role against the
role_permission join table.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models import Employee

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_employee(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Employee:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise credentials_error
    employee = db.get(Employee, payload["sub"])
    if not employee:
        raise credentials_error
    return employee


def require_permission(permission_code: str):
    def _check(employee: Employee = Depends(get_current_employee)) -> Employee:
        role_perm_codes = {p.code for p in employee.role.permissions}
        if permission_code not in role_perm_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{employee.role_code}' lacks permission '{permission_code}'",
            )
        return employee

    return _check
