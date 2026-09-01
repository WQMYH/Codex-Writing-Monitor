# Writing Ops

Writing Ops is a local Codex plugin for planning, supervising, reviewing, and tracing Storyforge writing runs.

The first implementation milestone is a host probe: it exposes a read-only `writing_dashboard` MCP tool and an MCP Apps dashboard resource. Every durable output remains `human_review_status=pending` until the user explicitly reviews it.

## Development

```powershell
uv sync --project server --dev
uv run --project server pytest
npm --prefix ui install
npm --prefix ui test -- --run
npm --prefix ui run build
```

Materialize an installable cache source with:

```powershell
uv run --project server python scripts/materialize_plugin.py
```

The repo-local marketplace must point to `.dist/current`, never the development checkout.

Because the cachebuster changes `plugin.json`, installation preparation is an ordered gate:

1. materialize `.dist/current`;
2. run the plugin-creator cachebuster updater against `.dist/current`;
3. run `uv run --frozen --project server python scripts/seal_plugin.py .dist/current`;
4. validate, install, then run `scripts/smoke_mcp.py` against the installed cache.

The smoke refuses to start the MCP server when any sealed file differs from `bundle-manifest.json`.
