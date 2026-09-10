"""Access-control tables: employees, roles, permissions.

Seeded from employee_master.csv. Roles map 1:1 to the `role` column in that
file today, but are kept as a separate table + role_permission join so that
permission checks in the API go through a lookup rather than string
comparisons scattered across routers.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Table, Column, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_code", ForeignKey("app_role.code"), primary_key=True),
    Column("permission_code", ForeignKey("permission.code"), primary_key=True),
)


class AppRole(Base):
    __tablename__ = "app_role"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    # Ordinal position in the business approval chain; NULL for roles that
    # never sit in the RM -> HoD -> HoDiv -> MD chain (EMPLOYEE, FINANCE).
    approval_level: Mapped[int | None] = mapped_column(nullable=True)

    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permission, back_populates="roles"
    )
    employees: Mapped[list["Employee"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permission"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))

    roles: Mapped[list["AppRole"]] = relationship(
        secondary=role_permission, back_populates="permissions"
    )


class Employee(Base):
    __tablename__ = "employee"

    emp_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    designation: Mapped[str] = mapped_column(String(128))
    department: Mapped[str] = mapped_column(String(64))
    cost_centre: Mapped[str] = mapped_column(String(16))
    city: Mapped[str] = mapped_column(String(64))
    reporting_manager_code: Mapped[str | None] = mapped_column(
        ForeignKey("employee.emp_code"), nullable=True
    )
    role_code: Mapped[str] = mapped_column(ForeignKey("app_role.code"))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    role: Mapped["AppRole"] = relationship(back_populates="employees")
    reporting_manager: Mapped["Employee | None"] = relationship(
        remote_side="Employee.emp_code", foreign_keys=[reporting_manager_code]
    )
