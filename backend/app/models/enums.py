"""Shared enums for the domain models. Plain str Enums so they serialise
cleanly through Pydantic/JSON without extra converters.
"""
from enum import Enum


class TravelRequestStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ClaimStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    PENDING_FINANCE = "PENDING_FINANCE"
    RETURNED = "RETURNED"
    REJECTED = "REJECTED"
    VERIFIED = "VERIFIED"
    PAID = "PAID"


class ClaimSection(str, Enum):
    LODGING = "LODGING"
    TRANSPORT = "TRANSPORT"
    OTHER = "OTHER"


class PaidBy(str, Enum):
    EMPLOYEE = "Employee"
    COMPANY = "Company"


class DocType(str, Enum):
    TRAVEL_APPROVAL_REQUEST = "TRAVEL_APPROVAL_REQUEST"
    TRAVEL_APPROVAL_GRANTED = "TRAVEL_APPROVAL_GRANTED"
    ADVANCE_NOTICE = "ADVANCE_NOTICE"
    FLIGHT_TICKET = "FLIGHT_TICKET"
    HOTEL_VOUCHER = "HOTEL_VOUCHER"
    HOTEL_INVOICE = "HOTEL_INVOICE"
    CAB_RECEIPT = "CAB_RECEIPT"
    MEAL_BILL = "MEAL_BILL"
    BUSINESS_ENTERTAINMENT_BILL = "BUSINESS_ENTERTAINMENT_BILL"
    PAYMENT_FAILURE_NOTICE = "PAYMENT_FAILURE_NOTICE"
    THIRD_PARTY_FORWARD = "THIRD_PARTY_FORWARD"
    PROMOTIONAL_NOISE = "PROMOTIONAL_NOISE"
    OTHER = "OTHER"


class ExtractionMode(str, Enum):
    BEDROCK = "BEDROCK"
    REGEX_FALLBACK = "REGEX_FALLBACK"
    MANUAL = "MANUAL"


class FlagSeverity(str, Enum):
    BLOCK = "BLOCK"
    WARN = "WARN"
    INFO = "INFO"


class ApprovalStepStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"
    SKIPPED = "SKIPPED"


class ApprovalStepType(str, Enum):
    BUSINESS = "BUSINESS"
    FINANCE_VERIFICATION = "FINANCE_VERIFICATION"


class PaymentStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    PAID = "PAID"
