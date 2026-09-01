from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from writing_ops.models import DashboardSnapshot, ProbeStatus


class WritingOpsService:
    """Read-only M0 service used to prove the Codex host integration."""

    def __init__(self, plugin_root: Path | None = None) -> None:
        configured_root = plugin_root or Path(os.environ.get("WRITING_OPS_PLUGIN_ROOT", ""))
        self._plugin_root = configured_root if str(configured_root) else Path(__file__).parents[3]

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
            milestone_state="review_ready",
            independent_review_status="failed",
            probes=probes,
            completed=[
                "插件脚手架",
                "只读 MCP 工具",
                "物化缓存安装",
                "固定任务与文本兜底",
                "定时任务插件可见性",
            ],
            pending=["第一轮审阅 finding 修复后的独立复核", "人工审阅"],
            blocked=[],
            next_action="冻结修复 CommitSet，并由新的独立审阅者复核 M0。",
            text_dashboard="",
        )
        snapshot.text_dashboard = self._render_text(snapshot)
        return snapshot

    @staticmethod
    def _render_text(snapshot: DashboardSnapshot) -> str:
        probe_lines = "; ".join(
            f"{probe.component}={probe.state}" for probe in snapshot.probes
        )
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
            f"独立审阅：{snapshot.independent_review_status}\n"
            f"人工审阅：{snapshot.human_review_status}"
        )
