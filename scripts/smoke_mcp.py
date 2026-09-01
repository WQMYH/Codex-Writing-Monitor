from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def smoke(plugin_root: Path) -> None:
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
            payload = {
                "tools": sorted(tool.name for tool in tools.tools),
                "dashboardHasStructuredContent": result.structuredContent is not None,
                "humanReviewStatus": (result.structuredContent or {}).get(
                    "human_review_status"
                ),
                "resources": [str(resource.uri) for resource in resources.resources],
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plugin_root", type=Path)
    args = parser.parse_args()
    asyncio.run(smoke(args.plugin_root))


if __name__ == "__main__":
    main()
