from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
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
from writing_ops.review_packet import gate_receipt_from_review
from writing_ops.state import GoalLevel, StateStore


class WritingOpsService:
    """Read-only M0 service used to prove the Codex host integration."""

    def __init__(
        self,
        plugin_root: Path | None = None,
        store: StateStore | None = None,
        adapter: WritingHostAdapter | None = None,
        runtime_config_path: Path | None = None,
        edge_executable: Path | None = None,
    ) -> None:
        configured_root = plugin_root or Path(os.environ.get("WRITING_OPS_PLUGIN_ROOT", ""))
        self._plugin_root = configured_root if str(configured_root) else Path(__file__).parents[3]
        self.store = store or StateStore()
        self.adapter = adapter or FakeWritingHostAdapter()
        self._runtime_session: Any | None = None
        self._runtime_failure_reason: str | None = None
        self._runtime_config_path = (
            runtime_config_path or self.store.database_path.parent / "runtime.json"
        )
        self._edge_executable = edge_executable

    @property
    def plugin_root(self) -> Path:
        return self._plugin_root

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
        if self._runtime_session is not None:
            reconciliation = self._runtime_session.reconciliation()
            running = all(state == "running" for state in reconciliation.values())
            status = {
                "adapter": "runtime-supervisor",
                "state": "running" if running else "blocked",
                "loopback": reconciliation["loopback"],
                "storyforge": {
                    "pid": self._runtime_session.storyforge.identity.pid,
                    "configuration_fingerprint": (
                        self._runtime_session.storyforge.configuration_fingerprint
                    ),
                },
                "edge": {"pid": self._runtime_session.edge.identity.pid, "profile": "owned"},
                "browser_worker": {
                    "pid": self._runtime_session.browser_harness.identity.pid,
                    "state": reconciliation["browser_worker"],
                    "browser_use_version": (
                        self._runtime_session.browser_harness.browser_use_version
                    ),
                    "autonomous_agent": False,
                },
                "reconciliation": reconciliation,
                "human_review_status": "pending",
            }
            if not running:
                status["reason"] = "runtime_component_stopped"
            return status
        if self._runtime_failure_reason is not None:
            return {
                "adapter": "runtime-supervisor",
                "state": "blocked",
                "reason": self._runtime_failure_reason,
                "human_review_status": "pending",
            }
        return self.adapter.runtime_status()

    def runtime_start(self) -> dict[str, Any]:
        if self._runtime_session is not None or self._runtime_failure_reason is not None:
            return self.runtime_status()
        if not self._runtime_config_path.is_file():
            return {
                "state": "blocked",
                "reason": "runtime_configuration_missing",
                "human_review_status": "pending",
            }
        from writing_ops.adapters import build_edge_launch_spec
        from writing_ops.runtime import launch_runtime_session, load_runtime_configuration

        try:
            configuration = load_runtime_configuration(self._runtime_config_path)
        except (OSError, ValueError):
            return {
                "state": "blocked",
                "reason": "runtime_configuration_invalid",
                "human_review_status": "pending",
            }
        try:
            edge_spec = build_edge_launch_spec(
                edge_executable=self._edge_executable or self._find_edge_executable(),
                runtime_root=self.store.database_path.parent,
                storyforge_origin=configuration.storyforge_origin,
            )
            self._runtime_session = launch_runtime_session(
                service=self,
                plugin_root=self.plugin_root,
                configuration=configuration,
                edge_spec=edge_spec,
                supervisor_nonce=secrets.token_urlsafe(24),
            )
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
            self._runtime_failure_reason = "runtime_start_failed"
            return self.runtime_status()
        return self.runtime_status()

    def runtime_stop(self) -> dict[str, Any]:
        if self._runtime_session is not None:
            self._runtime_session.close()
            self._runtime_session = None
        self._runtime_failure_reason = None
        return {
            "adapter": "runtime-supervisor",
            "state": "stopped",
            "human_review_status": "pending",
        }

    @staticmethod
    def _find_edge_executable() -> Path:
        candidates: list[Path] = []
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            ) as key:
                candidates.append(Path(str(winreg.QueryValue(key, None))))
        except OSError:
            pass
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            if root := os.environ.get(variable):
                candidates.append(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
        for candidate in candidates:
            if candidate.is_file() and candidate.name.lower() == "msedge.exe":
                return candidate
        raise FileNotFoundError("Microsoft Edge executable was not found")

    def human_review_submit(
        self, subject_type: str, subject_id: str, status: str, comment: str
    ) -> dict[str, Any]:
        return self.store.submit_human_review(subject_type, subject_id, status, comment)

    def record_review_verdict(
        self,
        *,
        run_id: str,
        packet: dict[str, Any],
        verdict: dict[str, Any],
        deterministic_checks: dict[str, bool],
        required_dimensions: list[str],
        configured_model: str,
        task_id: str,
        revision_count: int,
    ) -> dict[str, Any]:
        payload = gate_receipt_from_review(
            run_id=run_id,
            packet=packet,
            verdict=verdict,
            deterministic_checks=deterministic_checks,
            required_dimensions=required_dimensions,
            configured_model=configured_model,
            task_id=task_id,
            revision_count=revision_count,
        )
        return self.store.record_gate_receipt(run_id, payload)

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
        artifacts = self.store.list_artifacts()
        trace_events = self.store.list_trace_events()
        gate_receipts = self.store.list_gate_receipts()
        commit_sets = self.store.list_commit_sets()
        milestone_reviews = self.store.list_milestone_reviews()
        human_reviews = self.store.list_human_reviews()
        verified_m2 = [
            item
            for item in commit_sets
            if item["milestone_id"] == "M2" and item["integrity_status"] == "verified"
        ]
        latest_commit_set = verified_m2[-1] if verified_m2 else None
        latest_review = None
        if latest_commit_set is not None:
            matching_reviews = [
                item
                for item in milestone_reviews
                if item["commit_set_id"] == latest_commit_set["id"]
            ]
            latest_review = matching_reviews[-1] if matching_reviews else None
        human_review_status = (
            latest_commit_set["human_review_status"] if latest_commit_set else "pending"
        )

        completed = [
            "M0 宿主探针",
            "M1 核心契约",
            "M2 共享 ViewModel",
            "M2 Artifact 与 Trace",
            "M2 Storyforge fallback",
        ]
        blocked: list[str] = []
        if latest_commit_set is None:
            milestone_state = "implementing"
            independent_review_status = "pending"
            pending = ["M2 严格 CommitSet", "M2 独立审阅"]
            next_action = "冻结严格 M2 CommitSet，并进入独立审阅。"
        elif latest_review is None:
            milestone_state = "review_ready"
            independent_review_status = "pending"
            pending = ["M2 独立审阅", "M2 人工审阅"]
            next_action = "等待 M2 独立审阅；所有产出仍待人工审阅。"
        elif latest_review["verdict"] in {"passed", "passed_with_findings"}:
            independent_review_status = "passed"
            if human_review_status == "rejected":
                milestone_state = "implementing"
                pending = ["M2 人工拒绝修复", "M2 重新门禁与复核"]
                blocked = ["human_review_rejected"]
                next_action = "修复被人工拒绝的 M2 CommitSet，并重新执行门禁与复核。"
            else:
                milestone_state = "completed"
                pending = ["M2 人工审阅"] if human_review_status == "pending" else []
                next_action = (
                    "M2 独立审阅通过；可进入 M3，M2 仍保留显式人工审阅状态。"
                )
                completed.append("M2 独立审阅")
        else:
            milestone_state = "implementing"
            independent_review_status = "failed"
            pending = ["M2 修复", "M2 复核", "M2 人工审阅"]
            blocked = [
                str(finding.get("id", "unidentified"))
                for finding in latest_review["findings"]
                if finding.get("disposition") == "block_now"
            ]
            next_action = "修复 M2 block_now findings，冻结新 CommitSet 后复核。"

        artifact_statuses = {item["human_review_status"] for item in artifacts}
        creator_review_status = (
            "rejected"
            if "rejected" in artifact_statuses
            else "pending"
            if not artifact_statuses or "pending" in artifact_statuses
            else "approved"
        )
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
                state="available",
                detail=(
                    "The fixed fallback mount and shared renderer contract passed; "
                    "runtime lifecycle remains M4 work."
                ),
            ),
        ]
        snapshot = DashboardSnapshot(
            plugin_version=plugin_version,
            build_id=build_id,
            milestone="M2",
            milestone_state=milestone_state,
            independent_review_status=independent_review_status,
            human_review_status=human_review_status,
            probes=probes,
            completed=completed,
            pending=pending,
            blocked=blocked,
            next_action=next_action,
            text_dashboard="",
            creator=CreatorDashboardView(
                goals=GoalHierarchyView(
                    long_term=self.store.list_goal_revisions("long_term"),
                    cycle=self.store.list_goal_revisions("cycle"),
                    daily=self.store.list_goal_revisions("daily"),
                ),
                artifacts=artifacts,
                human_review_status=creator_review_status,
            ),
            reviewer=ReviewerDashboardView(
                trace_events=trace_events,
                gate_receipts=gate_receipts,
                commit_sets=commit_sets,
                milestone_reviews=milestone_reviews,
                human_reviews=human_reviews,
                human_review_status=human_review_status,
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
        gate_receipt_lines = "; ".join(
            f"{receipt.id}:{receipt.payload.gate_status}:{receipt.human_review_status}"
            for receipt in snapshot.reviewer.gate_receipts
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
            f"GateReceipt：{gate_receipt_lines}\n"
            f"CommitSet：{commit_set_lines}\n"
            f"里程碑审阅：{review_lines}\n"
            f"独立审阅：{snapshot.independent_review_status}\n"
            f"人工审阅：{snapshot.human_review_status}"
        )
