from datetime import date

from pydantic import BaseModel


class TravelRequestCreate(BaseModel):
    from_date: date
    to_date: date
    visiting_place: str
    city: str
    purpose: str
    mode_of_travel: str = "Flight"
    is_international: bool = False
    estimated_total: float = 0
    advance_requested: float = 0


class DocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    sender: str | None
    subject: str | None
    doc_type: str | None
    discarded: bool
    discard_reason: str | None
    extraction_mode: str | None

    model_config = {"from_attributes": True}


class TravelRequestOut(BaseModel):
    id: int
    travel_request_no: str
    employee_code: str
    from_date: date
    to_date: date
    visiting_place: str
    city: str
    purpose: str
    mode_of_travel: str
    is_international: bool
    estimated_total: float
    advance_requested: float
    status: str

    model_config = {"from_attributes": True}
