from __future__ import annotations

import html
import sys
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from writing_ops.loopback import load_verified_ui_component
from writing_ops.models import DashboardSnapshot
from writing_ops.service import WritingOpsService

UI_URI = "ui://writing-ops/dashboard.html"


def _read_only_annotations() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def _write_annotations(*, destructive: bool = False) -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=destructive,
        idempotentHint=False,
        openWorldHint=False,
    )


def create_server(service: WritingOpsService | None = None) -> FastMCP:
    app = FastMCP(
        "Writing Ops",
        instructions=(
            "Show the Writing Ops status ledger. Runtime start and stop require explicit host "
            "confirmation and use only the fixed local runtime configuration; no tool accepts "
            "a command, URL, JavaScript, or selector."
        ),
    )
    writing_ops = service or WritingOpsService()

    @app.tool(
        name="writing_dashboard",
        annotations=_read_only_annotations(),
        meta={
            "ui": {
                "visibility": ["model", "app"],
                "resourceUri": UI_URI,
            }
        },
        structured_output=True,
    )
    def writing_dashboard() -> DashboardSnapshot:
        """Open the read-only Writing Ops implementation and runtime ledger."""
        return writing_ops.dashboard()

    @app.tool(name="writing_goal_get", annotations=_read_only_annotations())
    def writing_goal_get(
        level: Literal["long_term", "cycle", "daily"],
        goal_id: str,
        revision: int | None = None,
    ) -> dict[str, Any]:
        """Read one immutable goal revision, or the latest revision when omitted."""
        return writing_ops.goal_get(level, goal_id, revision)

    @app.tool(name="writing_runtime_status", annotations=_read_only_annotations())
    def writing_runtime_status() -> dict[str, Any]:
        """Read the supervised runtime status; starts no process."""
        return writing_ops.runtime_status()

    @app.tool(name="writing_run_get", annotations=_read_only_annotations())
    def writing_run_get(run_id: str) -> dict[str, Any]:
        return writing_ops.pending_contract(f"writing_run_get:{run_id}")

    @app.tool(name="writing_trace_get", annotations=_read_only_annotations())
    def writing_trace_get(run_id: str) -> dict[str, Any]:
        return writing_ops.pending_contract(f"writing_trace_get:{run_id}")

    @app.tool(name="writing_milestone_get", annotations=_read_only_annotations())
    def writing_milestone_get(milestone_id: str) -> dict[str, Any]:
        return writing_ops.pending_contract(f"writing_milestone_get:{milestone_id}")

    @app.tool(name="writing_goal_upsert", annotations=_write_annotations())
    def writing_goal_upsert(
        level: Literal["long_term", "cycle", "daily"],
        payload: dict[str, Any],
        goal_id: str | None = None,
        long_term_id: str | None = None,
        long_term_revision: int | None = None,
        cycle_id: str | None = None,
        cycle_revision: int | None = None,
    ) -> dict[str, Any]:
        """Create a new immutable goal revision; never overwrites an earlier revision."""
        return writing_ops.goal_upsert(
            level,
            payload,
            goal_id=goal_id,
            long_term_id=long_term_id,
            long_term_revision=long_term_revision,
            cycle_id=cycle_id,
            cycle_revision=cycle_revision,
        )

    @app.tool(name="writing_goal_approve", annotations=_write_annotations())
    def writing_goal_approve(
        daily_goal_id: str, daily_revision: int, timezone: str, expires_at: str
    ) -> dict[str, Any]:
        """Approve one complete daily payload bound to all three goal revisions."""
        return writing_ops.goal_approve(daily_goal_id, daily_revision, timezone, expires_at)

    @app.tool(name="writing_run_start", annotations=_write_annotations())
    def writing_run_start(daily_goal_id: str, daily_revision: int) -> dict[str, Any]:
        return writing_ops.pending_contract(f"writing_run_start:{daily_goal_id}:{daily_revision}")

    @app.tool(name="writing_run_cancel", annotations=_write_annotations(destructive=True))
    def writing_run_cancel(run_id: str) -> dict[str, Any]:
        return writing_ops.pending_contract(f"writing_run_cancel:{run_id}")

    @app.tool(name="writing_runtime_start", annotations=_write_annotations())
    def writing_runtime_start() -> dict[str, Any]:
        """Start only the runtime named by the sealed local configuration."""
        return writing_ops.runtime_start()

    @app.tool(name="writing_runtime_stop", annotations=_write_annotations(destructive=True))
    def writing_runtime_stop() -> dict[str, Any]:
        """Stop only the runtime session currently owned by this process."""
        return writing_ops.runtime_stop()

    @app.tool(name="writing_human_review_submit", annotations=_write_annotations())
    def writing_human_review_submit(
        subject_type: str,
        subject_id: str,
        status: Literal["approved", "rejected"],
        comment: str = "",
    ) -> dict[str, Any]:
        """Record an explicit user decision for one allowlisted durable subject."""
        return writing_ops.human_review_submit(subject_type, subject_id, status, comment)

    @app.tool(name="writing_run_due", annotations=_write_annotations())
    def writing_run_due(
        action: Literal["claim", "poll", "submit_review", "reconcile"] = "claim",
        run_id: str | None = None,
        resume_token: str | None = None,
    ) -> dict[str, Any]:
        """Claim, poll, or reconcile one durable unattended Run protocol."""
        return writing_ops.run_due(action, run_id, resume_token)

    @app.resource(
        UI_URI,
        name="Writing Ops dashboard",
        description="Read-only Writing Ops host probe dashboard",
        mime_type="text/html;profile=mcp-app",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": [],
                    "frameDomains": [],
                    "baseUriDomains": [],
                },
                "prefersBorder": False,
            }
        },
    )
    def dashboard_resource() -> str:
        try:
            bundle = load_verified_ui_component(writing_ops.plugin_root).decode("utf-8")
        except (OSError, UnicodeError, ValueError):
            bundle = ""
        if bundle:
            bundle = bundle.replace("</script", "<\\/script")
            body = '<div id="root"></div><script type="module">' + bundle + "</script>"
        else:
            message = html.escape("Writing Ops UI bundle is missing. Use the text dashboard.")
            body = f'<main role="alert"><h1>写作运行台</h1><p>{message}</p></main>'
        return (
            '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>写作运行台</title></head><body>" + body + "</body></html>"
        )

    return app


def main() -> None:
    try:
        create_server().run(transport="stdio")
    except Exception as error:
        print(f"Writing Ops MCP failed: {error}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
