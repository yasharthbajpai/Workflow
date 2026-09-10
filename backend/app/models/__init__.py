"""Import every model module so Base.metadata is fully populated before
ensure_schema()/create_all() or Alembic autogenerate run.
"""
from app.models.access_control import AppRole, Employee, Permission, role_permission  # noqa: F401
from app.models.policy import ApprovalBand, CityTier, PolicyConfig  # noqa: F401
from app.models.travel import Advance, EstimateLine, TravelRequest  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.claim import Claim, ClaimLine, LinePolicyFlag  # noqa: F401
from app.models.approval import ApprovalStep, ClaimEvent, Payment  # noqa: F401

__all__ = [
    "AppRole",
    "Employee",
    "Permission",
    "role_permission",
    "ApprovalBand",
    "CityTier",
    "PolicyConfig",
    "Advance",
    "EstimateLine",
    "TravelRequest",
    "Document",
    "Claim",
    "ClaimLine",
    "LinePolicyFlag",
    "ApprovalStep",
    "ClaimEvent",
    "Payment",
]
