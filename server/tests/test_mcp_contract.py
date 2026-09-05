from __future__ import annotations

import json
from pathlib import Path

import pytest

from writing_ops.materialize import seal_bundle
from writing_ops.mcp_server import UI_URI, create_server
from writing_ops.service import WritingOpsService
from writing_ops.state import StateStore


def _plugin_root(
    tmp_path: Path,
    version: str = "0.1.0+codex.test",
    bundle: str = "document.querySelector('#root').textContent='loaded';",
) -> Path:
    root = tmp_path / "writing-ops"
    manifest = root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"version": version}), encoding="utf-8")
    component = root / "ui" / "dist" / "component.js"
    component.parent.mkdir(parents=True)
    component.write_text(bundle, encoding="utf-8")
    seal_bundle(root)
    return root


def test_dashboard_is_revision_bound_and_explicitly_pending_human_review(
    tmp_path: Path,
) -> None:
    snapshot = WritingOpsService(
        _plugin_root(tmp_path), store=StateStore(tmp_path / "state.sqlite3")
    ).dashboard()

    assert snapshot.milestone == "M2"
    assert snapshot.milestone_state == "implementing"
    assert snapshot.independent_review_status == "pending"
    assert snapshot.plugin_version == "0.1.0+codex.test"
    assert snapshot.build_id.startswith("sha256:")
    assert snapshot.ui_resource_uri == UI_URI
    assert snapshot.human_review_status == "pending"
    assert snapshot.blocked == []
    assert "scheduled-task=available" in snapshot.text_dashboard
    assert snapshot.plugin_version in snapshot.text_dashboard
    assert snapshot.build_id in snapshot.text_dashboard
    assert snapshot.next_action in snapshot.text_dashboard
    assert "人工审阅：pending" in snapshot.text_dashboard


@pytest.mark.asyncio
async def test_mcp_exposes_read_only_dashboard_and_app_resource(
    tmp_path: Path,
) -> None:
    app = create_server(
        WritingOpsService(
            _plugin_root(tmp_path), store=StateStore(tmp_path / "state.sqlite3")
        )
    )

    tools = await app.list_tools()
    tool_names = {tool.name for tool in tools}
    assert {
        "writing_dashboard",
        "writing_goal_get",
        "writing_runtime_status",
        "writing_goal_upsert",
        "writing_goal_approve",
        "writing_run_due",
    } <= tool_names
    dashboard = next(tool for tool in tools if tool.name == "writing_dashboard")
    assert dashboard.annotations.readOnlyHint is True
    assert dashboard.annotations.destructiveHint is False
    assert dashboard.meta["ui"]["resourceUri"] == UI_URI
    assert dashboard.outputSchema["additionalProperties"] is False

    resources = await app.list_resources()
    resource = next(item for item in resources if str(item.uri) == UI_URI)
    assert resource.mimeType == "text/html;profile=mcp-app"

    contents = await app.read_resource(UI_URI)
    html = contents[0].content
    assert '<div id="root"></div>' in html
    assert "document.querySelector" in html
    assert contents[0].mime_type == "text/html;profile=mcp-app"


@pytest.mark.asyncio
async def test_mcp_runtime_tools_forward_to_the_fixed_runtime_service(tmp_path: Path) -> None:
    app = create_server(WritingOpsService(store=StateStore(tmp_path / "state.sqlite3")))

    _, start = await app.call_tool("writing_runtime_start", {})
    _, stop = await app.call_tool("writing_runtime_stop", {})

    assert start == {
        "state": "blocked",
        "reason": "runtime_configuration_missing",
        "human_review_status": "pending",
    }
    assert stop == {
        "adapter": "runtime-supervisor",
        "state": "stopped",
        "human_review_status": "pending",
    }
