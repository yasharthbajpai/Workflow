from pydantic import BaseModel


class StageCount(BaseModel):
    status: str
    count: int


class DashboardSummary(BaseModel):
    my_claims_count: int
    awaiting_my_action_count: int
    stage_counts: list[StageCount]
