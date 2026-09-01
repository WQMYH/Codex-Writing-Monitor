from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from writing_ops.materialize import verify_bundle


async def smoke(plugin_root: Path) -> None:
    verify_bundle(plugin_root)
    parameters = StdioServerParameters(
        command="powershell.exe",
        args=[
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "./scripts/run-mcp.ps1",
        ],
        cwd=str(plugin_root.resolve(strict=True)),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("writing_dashboard", {})
            resources = await session.list_resources()
            resource = await session.read_resource("ui://writing-ops/dashboard.html")
            resource_text = resource.contents[0].text
            dashboard = result.structuredContent or {}
            payload = {
                "tools": sorted(tool.name for tool in tools.tools),
                "dashboardHasStructuredContent": result.structuredContent is not None,
                "humanReviewStatus": dashboard.get("human_review_status"),
                "pluginVersion": dashboard.get("plugin_version"),
                "buildId": dashboard.get("build_id"),
                "textDashboardComplete": all(
                    marker in dashboard.get("text_dashboard", "")
                    for marker in ("插件版本：", "构建标识：", "探针：", "下一步：", "人工审阅：pending")
                ),
                "resources": [str(resource.uri) for resource in resources.resources],
                "resourceMimeType": resource.contents[0].mimeType,
                "resourceHasRoot": '<div id="root"></div>' in resource_text,
                "resourceHasBundle": "WRITING OPS" in resource_text,
            }
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            if payload["tools"] != ["writing_dashboard"]:
                raise RuntimeError(f"Unexpected M0 tools: {payload['tools']}")
            if "ui://writing-ops/dashboard.html" not in payload["resources"]:
                raise RuntimeError("Writing Ops dashboard resource missing")
            if not payload["dashboardHasStructuredContent"]:
                raise RuntimeError("Writing Ops dashboard structured result missing")
            if payload["humanReviewStatus"] != "pending":
                raise RuntimeError("Durable M0 output must remain pending human review")
            if not payload["pluginVersion"] or not payload["buildId"]:
                raise RuntimeError("Installed dashboard is not bound to a build identity")
            if not payload["textDashboardComplete"]:
                raise RuntimeError("Installed dashboard text fallback is incomplete")
            if payload["resourceMimeType"] != "text/html;profile=mcp-app":
                raise RuntimeError("Writing Ops dashboard resource MIME type is invalid")
            if not payload["resourceHasRoot"] or not payload["resourceHasBundle"]:
                raise RuntimeError("Writing Ops dashboard resource did not include the React bundle")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plugin_root", type=Path)
    args = parser.parse_args()
    asyncio.run(smoke(args.plugin_root))


if __name__ == "__main__":
    main()
