from __future__ import annotations

import html
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

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


def create_server(service: WritingOpsService | None = None) -> FastMCP:
    app = FastMCP(
        "Writing Ops",
        instructions=(
            "Show the Writing Ops status ledger. The M0 probe is read-only and never starts "
            "Storyforge, Edge, a browser worker, or a writing run."
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
        bundle_path = Path(os.environ.get("WRITING_OPS_UI_BUNDLE", ""))
        if bundle_path.is_file():
            bundle = bundle_path.read_text(encoding="utf-8").replace("</script", "<\\/script")
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

