from __future__ import annotations

import pytest

from writing_ops.mcp_server import UI_URI, create_server
from writing_ops.service import WritingOpsService


def test_dashboard_is_explicitly_pending_human_review() -> None:
    snapshot = WritingOpsService().dashboard()

    assert snapshot.milestone == "M0"
    assert snapshot.plugin_version == "0.1.0"
    assert snapshot.ui_resource_uri == UI_URI
    assert snapshot.human_review_status == "pending"
    assert snapshot.blocked == []
    assert "人工审阅：pending" in snapshot.text_dashboard


@pytest.mark.asyncio
async def test_mcp_exposes_read_only_dashboard_and_app_resource() -> None:
    app = create_server(WritingOpsService())

    tools = await app.list_tools()
    assert [tool.name for tool in tools] == ["writing_dashboard"]
    dashboard = tools[0]
    assert dashboard.annotations.readOnlyHint is True
    assert dashboard.annotations.destructiveHint is False
    assert dashboard.meta["ui"]["resourceUri"] == UI_URI
    assert dashboard.outputSchema["additionalProperties"] is False

    resources = await app.list_resources()
    resource = next(item for item in resources if str(item.uri) == UI_URI)
    assert resource.mimeType == "text/html;profile=mcp-app"
