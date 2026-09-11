from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class EstimateLineIn(BaseModel):
    """One row of section 3 (ESTIMATED COST) on Form NTX-TRF-02."""

    head: str
    basis: str = ""
    estimate: float = 0
    borne_by: Literal["Employee", "Company"] = "Company"


class EstimateLineOut(EstimateLineIn):
    id: int

    model_config = {"from_attributes": True}


class TravelRequestCreate(BaseModel):
    from_date: date
    to_date: date
    visiting_place: str
    city: str
    purpose: str
    mode_of_travel: str = "Flight"
    is_international: bool = False
    advance_requested: float = 0
    # estimated_total is NOT taken from the client: it is the form's =SUM()
    # over these lines and is computed server-side, so the stored header
    # figure can never disagree with the breakdown that justifies it.
    estimate_lines: list[EstimateLineIn] = Field(default_factory=list)


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
    estimate_lines: list[EstimateLineOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}
