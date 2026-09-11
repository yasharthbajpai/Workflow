from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class EmployeeOut(BaseModel):
    emp_code: str
    name: str
    email: str
    designation: str
    department: str
    cost_centre: str
    city: str
    role_code: str
    reporting_manager_code: str | None = None
    reporting_manager_name: str | None = None

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    employee: EmployeeOut
