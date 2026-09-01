from __future__ import annotations

from writing_ops.models import DashboardSnapshot, ProbeStatus


class WritingOpsService:
    """Read-only M0 service used to prove the Codex host integration."""

    def dashboard(self) -> DashboardSnapshot:
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
                component="storyforge",
                state="not_tested",
                detail="Runtime control is outside M0.",
            ),
        ]
        text = (
            "写作运行台 · M0 implementing\n"
            "完成：插件脚手架、只读 MCP 探针、物化缓存安装、文本兜底\n"
            "未验证：Codex 任务内 MCP Apps 组件渲染\n"
            "待做：定时插件可见性、独立审阅\n"
            "人工审阅：pending"
        )
        return DashboardSnapshot(
            probes=probes,
            completed=["插件脚手架", "只读 MCP 工具", "缓存安装", "文本兜底"],
            pending=["定时插件可见性", "独立审阅"],
            blocked=[],
            next_action="构建并安装 M0 宿主探针。",
            text_dashboard=text,
        )
