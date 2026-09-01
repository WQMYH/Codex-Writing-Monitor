from __future__ import annotations

import json
from pathlib import Path

import pytest

from writing_ops.mcp_server import UI_URI, create_server
from writing_ops.service import WritingOpsService


def _plugin_root(tmp_path: Path, version: str = "0.1.0+codex.test") -> Path:
    root = tmp_path / "writing-ops"
    manifest = root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"version": version}), encoding="utf-8")
    (root / "bundle-manifest.json").write_text("{}", encoding="utf-8")
    return root


def test_dashboard_is_revision_bound_and_explicitly_pending_human_review(
    tmp_path: Path,
) -> None:
    snapshot = WritingOpsService(_plugin_root(tmp_path)).dashboard()

    assert snapshot.milestone == "M0"
    assert snapshot.milestone_state == "completed"
    assert snapshot.independent_review_status == "passed"
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "component.js"
    bundle.write_text("document.querySelector('#root').textContent='loaded';", encoding="utf-8")
    monkeypatch.setenv("WRITING_OPS_UI_BUNDLE", str(bundle))
    app = create_server(WritingOpsService(_plugin_root(tmp_path)))

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

    contents = await app.read_resource(UI_URI)
    html = contents[0].content
    assert '<div id="root"></div>' in html
    assert "document.querySelector" in html
    assert contents[0].mime_type == "text/html;profile=mcp-app"
