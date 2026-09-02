from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from writing_ops.adapters import FakeWritingHostAdapter, WritingHostAdapter
from writing_ops.models import (
    CreatorDashboardView,
    DashboardSnapshot,
    GoalHierarchyView,
    ProbeStatus,
    ReviewerDashboardView,
)
from writing_ops.state import GoalLevel, StateStore


class WritingOpsService:
    """Read-only M0 service used to prove the Codex host integration."""

    def __init__(
        self,
        plugin_root: Path | None = None,
        store: StateStore | None = None,
        adapter: WritingHostAdapter | None = None,
    ) -> None:
        configured_root = plugin_root or Path(os.environ.get("WRITING_OPS_PLUGIN_ROOT", ""))
        self._plugin_root = configured_root if str(configured_root) else Path(__file__).parents[3]
        self.store = store or StateStore()
        self.adapter = adapter or FakeWritingHostAdapter()

    def goal_upsert(
        self, level: GoalLevel, payload: dict[str, Any], **links: Any
    ) -> dict[str, Any]:
        return self.store.upsert_goal(level, payload, **links)

    def goal_get(self, level: GoalLevel, goal_id: str, revision: int | None) -> dict[str, Any]:
        goal = self.store.get_goal(level, goal_id, revision)
        return goal or {"status": "not_found", "human_review_status": "pending"}

    def goal_approve(
        self, daily_goal_id: str, daily_revision: int, timezone: str, expires_at: str
    ) -> dict[str, Any]:
        from datetime import datetime

        return self.store.approve_daily_goal(
            daily_goal_id, daily_revision, timezone, datetime.fromisoformat(expires_at)
        )

    def runtime_status(self) -> dict[str, Any]:
        return self.adapter.runtime_status()

    def human_review_submit(
        self, subject_type: str, subject_id: str, status: str, comment: str
    ) -> dict[str, Any]:
        return self.store.submit_human_review(subject_type, subject_id, status, comment)

    @staticmethod
    def pending_contract(operation: str) -> dict[str, Any]:
        return {
            "operation": operation,
            "status": "not_implemented",
            "required_milestone": "M2+",
            "human_review_status": "pending",
        }

    def _runtime_identity(self) -> tuple[str, str]:
        manifest_path = self._plugin_root / ".codex-plugin" / "plugin.json"
        manifest_bytes = manifest_path.read_bytes()
        version = str(json.loads(manifest_bytes)["version"])
        digest = hashlib.sha256()
        digest.update(manifest_bytes)
        bundle_manifest = self._plugin_root / "bundle-manifest.json"
        if bundle_manifest.is_file():
            digest.update(bundle_manifest.read_bytes())
        return version, f"sha256:{digest.hexdigest()}"

    def dashboard(self) -> DashboardSnapshot:
        plugin_version, build_id = self._runtime_identity()
        probes = [
            ProbeStatus(
                component="mcp-tool",
                state="available",
                detail="writing_dashboard returned a strict structured result.",
            ),
            ProbeStatus(
                component="installed-cache",
                state="available",
                detail="The cached plugin launched and served tools and resources over stdio.",
            ),
            ProbeStatus(
                component="codex-mcp-apps",
                state="not_tested",
                detail="A fresh task called the tool but could not prove component rendering.",
            ),
            ProbeStatus(
                component="text-fallback",
                state="available",
                detail="A fresh Codex task displayed the complete text dashboard.",
            ),
            ProbeStatus(
                component="scheduled-task",
                state="available",
                detail="A two-minute scheduled canary called writing_dashboard and paused itself.",
            ),
            ProbeStatus(
                component="storyforge",
                state="not_tested",
                detail="Runtime control is outside M0.",
            ),
        ]
        snapshot = DashboardSnapshot(
            plugin_version=plugin_version,
            build_id=build_id,
            milestone="M2",
            milestone_state="implementing",
            independent_review_status="pending",
            probes=probes,
            completed=[
                "M0 宿主探针",
                "M1 核心契约",
                "M2 共享 ViewModel",
                "M2 Artifact 与 Trace",
            ],
            pending=["Storyforge fallback", "M2 CommitSet 与独立审阅"],
            blocked=[],
            next_action="完成 Storyforge fallback，并冻结 M2 CommitSet 进入独立审阅。",
            text_dashboard="",
            creator=CreatorDashboardView(
                goals=GoalHierarchyView(
                    long_term=self.store.list_goal_revisions("long_term"),
                    cycle=self.store.list_goal_revisions("cycle"),
                    daily=self.store.list_goal_revisions("daily"),
                ),
                artifacts=self.store.list_artifacts(),
            ),
            reviewer=ReviewerDashboardView(
                trace_events=self.store.list_trace_events(),
                commit_sets=self.store.list_commit_sets(),
                milestone_reviews=self.store.list_milestone_reviews(),
                human_reviews=self.store.list_human_reviews(),
            ),
        )
        snapshot.text_dashboard = self._render_text(snapshot)
        return snapshot

    @staticmethod
    def _render_text(snapshot: DashboardSnapshot) -> str:
        probe_lines = "; ".join(
            f"{probe.component}={probe.state}" for probe in snapshot.probes
        )
        artifact_lines = "; ".join(
            f"{artifact.id}:{artifact.kind}:{artifact.sha256}"
            for artifact in snapshot.creator.artifacts
        ) or "无"
        trace_lines = "; ".join(
            f"{event.event_type}#{event.sequence}:{event.event_hash}"
            for event in snapshot.reviewer.trace_events
        ) or "无"
        commit_set_lines = "; ".join(
            f"{commit_set.id}:{commit_set.milestone_id}:revision-{commit_set.revision}:"
            f"{commit_set.human_review_status}"
            for commit_set in snapshot.reviewer.commit_sets
        ) or "无"
        review_lines = "; ".join(
            f"{review.id}:{review.verdict}:{len(review.findings)}-findings"
            for review in snapshot.reviewer.milestone_reviews
        ) or "无"
        return (
            f"{snapshot.title} · {snapshot.milestone} {snapshot.milestone_state}\n"
            f"插件版本：{snapshot.plugin_version}\n"
            f"构建标识：{snapshot.build_id}\n"
            f"资源：{snapshot.ui_resource_uri}\n"
            f"完成：{'、'.join(snapshot.completed)}\n"
            f"探针：{probe_lines}\n"
            "未验证：Codex 任务内 MCP Apps React 组件渲染\n"
            f"待做：{'、'.join(snapshot.pending)}\n"
            f"下一步：{snapshot.next_action}\n"
            "创作者模式：三级目标与写作产出\n"
            f"Artifact：{artifact_lines}\n"
            "审查模式：运行、Trace 与门禁\n"
            f"Trace：{trace_lines}\n"
            f"CommitSet：{commit_set_lines}\n"
            f"里程碑审阅：{review_lines}\n"
            f"独立审阅：{snapshot.independent_review_status}\n"
            f"人工审阅：{snapshot.human_review_status}"
        )
