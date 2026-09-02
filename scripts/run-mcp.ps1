$ErrorActionPreference = "Stop"
$pluginRoot = Split-Path -Parent $PSScriptRoot
$serverRoot = Join-Path $pluginRoot "server"
$env:WRITING_OPS_PLUGIN_ROOT = $pluginRoot

& uv run --frozen --project $serverRoot python -m writing_ops.mcp_server
exit $LASTEXITCODE
