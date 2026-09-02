from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProbeStatus(StrictModel):
    component: str
    state: Literal["available", "not_tested", "blocked"]
    detail: str


class GoalRevisionView(StrictModel):
    id: str
    revision: int
    payload: dict[str, Any]
    human_review_status: Literal["pending", "approved", "rejected"]


class GoalHierarchyView(StrictModel):
    long_term: list[GoalRevisionView]
    cycle: list[GoalRevisionView]
    daily: list[GoalRevisionView]


class CreatorDashboardView(StrictModel):
    goals: GoalHierarchyView
    human_review_status: Literal["pending", "approved", "rejected"] = "pending"


class ReviewerDashboardView(StrictModel):
    human_review_status: Literal["pending", "approved", "rejected"] = "pending"


class DashboardSnapshot(StrictModel):
    schema_version: int = 2
    title: str = "写作运行台"
    plugin_version: str = "0.1.0"
    build_id: str
    ui_resource_uri: str = "ui://writing-ops/dashboard.html"
    milestone: str = "M0"
    milestone_state: Literal[
        "implementing", "review_ready", "completed", "blocked"
    ] = "review_ready"
    independent_review_status: Literal["pending", "passed", "failed"] = "pending"
    human_review_status: Literal["pending", "approved", "rejected"] = "pending"
    probes: list[ProbeStatus]
    completed: list[str]
    pending: list[str]
    blocked: list[str]
    next_action: str
    text_dashboard: str
    creator: CreatorDashboardView
    reviewer: ReviewerDashboardView
