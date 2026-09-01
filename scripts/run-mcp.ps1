$ErrorActionPreference = "Stop"
$pluginRoot = Split-Path -Parent $PSScriptRoot
$serverRoot = Join-Path $pluginRoot "server"
$uiBundle = Join-Path $pluginRoot "ui\dist\component.js"

$env:WRITING_OPS_PLUGIN_ROOT = $pluginRoot
$env:WRITING_OPS_UI_BUNDLE = $uiBundle

& uv run --frozen --project $serverRoot python -m writing_ops.mcp_server
exit $LASTEXITCODE

