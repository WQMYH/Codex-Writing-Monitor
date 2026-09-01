from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProbeStatus(StrictModel):
    component: str
    state: Literal["available", "not_tested", "blocked"]
    detail: str


class DashboardSnapshot(StrictModel):
    schema_version: int = 1
    title: str = "写作运行台"
    plugin_version: str = "0.1.0"
    build_id: str
    ui_resource_uri: str = "ui://writing-ops/dashboard.html"
    milestone: str = "M0"
    milestone_state: Literal["implementing", "review_ready", "blocked"] = "review_ready"
    independent_review_status: Literal["pending", "passed", "failed"] = "pending"
    human_review_status: Literal["pending", "approved", "rejected"] = "pending"
    probes: list[ProbeStatus]
    completed: list[str]
    pending: list[str]
    blocked: list[str]
    next_action: str
    text_dashboard: str
