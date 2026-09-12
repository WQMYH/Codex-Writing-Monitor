from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ArtifactView(StrictModel):
    id: str
    run_id: str | None
    kind: str
    sha256: str
    created_at: str
    human_review_status: Literal["pending", "approved", "rejected"]
    integrity_status: Literal["verified"]


class TraceEventView(StrictModel):
    run_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]
    previous_hash: str | None
    event_hash: str
    created_at: str
    human_review_status: Literal["pending", "approved", "rejected"]
    integrity_status: Literal["verified"]


class GateReceiptView(StrictModel):
    id: str
    run_id: str
    payload: GateReceiptPayload
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str
    human_review_status: Literal["pending", "approved", "rejected"]
    integrity_status: Literal["verified"]


class RepositoryRange(StrictModel):
    base: str = Field(pattern=r"^[0-9a-f]{40}$")
    head: str = Field(pattern=r"^[0-9a-f]{40}$")


class WritingMcpBaseline(StrictModel):
    baseline: str = Field(pattern=r"^[0-9a-f]{40}$")
    modified: Literal[False]


class CommitSetRepositories(StrictModel):
    writing_ops: RepositoryRange
    storyforge: RepositoryRange
    writing_mcp: WritingMcpBaseline


class InstalledPluginReceipt(StrictModel):
    version: str = Field(min_length=1, max_length=128)
    build_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    marketplace: Literal["gameops-local"]
    sealed_smoke: Literal["passed"]


class ReviewPackageReceipt(StrictModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(gt=0)


class MachineGateReceipt(StrictModel):
    receipt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["passed"]


class GateFinding(StrictModel):
    severity: Literal["P0", "P1", "P2"]
    dimension: str | None = Field(default=None, min_length=1, max_length=128)


class ReviewVerdict(StrictModel):
    semantic_dimensions: dict[str, Literal["pass", "fail", "uncertain"]]
    findings: list[GateFinding]


def gate_status_for_evidence(
    deterministic_checks: dict[str, bool],
    required_dimensions: list[str],
    verdict: ReviewVerdict,
) -> Literal["passed", "blocked"]:
    required = set(required_dimensions)
    if (
        len(required) != len(required_dimensions)
        or set(verdict.semantic_dimensions) != required
        or not deterministic_checks
        or not all(deterministic_checks.values())
        or any(status != "pass" for status in verdict.semantic_dimensions.values())
        or any(finding.severity in {"P0", "P1"} for finding in verdict.findings)
        or any(
            finding.severity == "P2" and finding.dimension in required
            for finding in verdict.findings
        )
    ):
        return "blocked"
    return "passed"


class GateReceiptPayload(StrictModel):
    schema_version: Literal[1]
    run_id: str = Field(min_length=1, max_length=128)
    review_packet_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    configured_model: str = Field(min_length=1, max_length=256)
    task_id: str = Field(min_length=1, max_length=256)
    prompt_version: str = Field(min_length=1, max_length=128)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    deterministic_checks: dict[str, bool] = Field(min_length=1)
    required_dimensions: list[str] = Field(min_length=1)
    semantic_dimensions: dict[str, Literal["pass", "fail", "uncertain"]]
    findings: list[GateFinding]
    revision_count: int = Field(ge=0, le=2)
    gate_status: Literal["passed", "blocked"]
    human_review_status: Literal["pending"]

    @model_validator(mode="after")
    def gate_status_matches_evidence(self) -> GateReceiptPayload:
        expected = gate_status_for_evidence(
            self.deterministic_checks,
            self.required_dimensions,
            ReviewVerdict(
                semantic_dimensions=self.semantic_dimensions,
                findings=self.findings,
            ),
        )
        if self.gate_status == "passed" and expected != "passed":
            raise ValueError("passed GateReceipt requires complete passing evidence")
        return self


class CommitSetPayload(StrictModel):
    schema_version: Literal[1]
    milestone_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(gt=0)
    repositories: CommitSetRepositories
    installed_plugin: InstalledPluginReceipt
    review_package: ReviewPackageReceipt
    machine_gate: MachineGateReceipt
    human_review_status: Literal["pending"]


class CommitSetView(StrictModel):
    id: str
    milestone_id: str
    revision: int
    payload: CommitSetPayload | None
    payload_hash: str
    created_at: str
    human_review_status: Literal["pending", "approved", "rejected"]
    integrity_status: Literal["verified", "legacy_unverified"]


class MilestoneReviewView(StrictModel):
    id: str
    milestone_id: str
    commit_set_id: str
    verdict: Literal["passed", "passed_with_findings", "failed", "blocked"]
    findings: list[dict[str, Any]]
    created_at: str
    human_review_status: Literal["pending", "approved", "rejected"]


class HumanReviewView(StrictModel):
    id: str
    subject_type: str
    subject_id: str
    status: Literal["approved", "rejected"]
    comment: str | None
    created_at: str


class CreatorDashboardView(StrictModel):
    goals: GoalHierarchyView
    artifacts: list[ArtifactView]
    human_review_status: Literal["pending", "approved", "rejected"] = "pending"


class ReviewerDashboardView(StrictModel):
    trace_events: list[TraceEventView]
    gate_receipts: list[GateReceiptView]
    commit_sets: list[CommitSetView]
    milestone_reviews: list[MilestoneReviewView]
    human_reviews: list[HumanReviewView]
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
