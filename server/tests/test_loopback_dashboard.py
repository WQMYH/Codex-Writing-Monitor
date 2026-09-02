from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from writing_ops.loopback import create_dashboard_loopback_app, create_loopback_server
from writing_ops.materialize import seal_bundle
from writing_ops.service import WritingOpsService
from writing_ops.state import StateStore

SESSION_TOKEN = "session_abcdefghijklmnopqrstuvwxyz_123456"
CSRF_TOKEN = "csrf_zyxwvutsrqponmlkjihgfedcba_654321"

def call_app(
    app,
    *,
    method: str = "GET",
    path: str = "/api/writing-ops/dashboard",
    origin: str = "http://127.0.0.1:5173",
    session: str | None = SESSION_TOKEN,
    csrf: str | None = CSRF_TOKEN,
    private_network: bool = False,
) -> tuple[int, dict[str, str], bytes]:
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = int(status.split()[0])
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "wsgi.input": BytesIO(),
        "HTTP_ORIGIN": origin,
    }
    if session is not None:
        environ["HTTP_X_WRITING_OPS_SESSION"] = session
    if csrf is not None:
        environ["HTTP_X_WRITING_OPS_CSRF"] = csrf
    if private_network:
        environ["HTTP_ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK"] = "true"
    body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], body


def service(tmp_path: Path) -> WritingOpsService:
    return WritingOpsService(store=StateStore(tmp_path / "state.sqlite3"))


def sealed_plugin(tmp_path: Path) -> tuple[Path, bytes]:
    root = tmp_path / "writing-ops"
    bundle = root / "ui" / "dist" / "component.js"
    bundle.parent.mkdir(parents=True)
    body = b"document.body.dataset.writingOps = 'loaded';"
    bundle.write_bytes(body)
    manifest = root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name":"writing-ops","version":"0.1.0+codex.test"}')
    seal_bundle(root)
    return root, body


def test_loopback_dashboard_requires_exact_origin_memory_tokens_and_csrf(tmp_path) -> None:
    root, _ = sealed_plugin(tmp_path)
    launch = create_dashboard_loopback_app(
        service(tmp_path),
        plugin_root=root,
        storyforge_origin="http://127.0.0.1:5173",
    )
    app = launch.app

    status, headers, body = call_app(
        app, session=launch.session_token, csrf=launch.csrf_token
    )
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert headers["Cache-Control"] == "no-store"
    assert json.loads(body)["schema_version"] == 2
    assert launch.session_token.encode() not in body and launch.csrf_token.encode() not in body

    assert call_app(app, origin="http://evil.example")[0] == 403
    assert call_app(app, session=None)[0] == 401
    assert call_app(app, session=launch.session_token, csrf=None)[0] == 403
    assert call_app(app, method="POST")[0] == 405


def test_loopback_preflight_is_exact_and_server_cannot_bind_non_loopback(tmp_path) -> None:
    root, _ = sealed_plugin(tmp_path)
    launch = create_dashboard_loopback_app(
        service(tmp_path),
        plugin_root=root,
        storyforge_origin="http://127.0.0.1:5173",
    )
    app = launch.app

    status, headers, _ = call_app(
        app, method="OPTIONS", session=None, csrf=None, private_network=True
    )
    assert status == 204
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert headers["Access-Control-Allow-Private-Network"] == "true"
    assert headers["Access-Control-Allow-Headers"] == (
        "X-Writing-Ops-Session, X-Writing-Ops-CSRF"
    )
    assert call_app(app, method="OPTIONS", origin="http://evil.example")[0] == 403

    with pytest.raises(ValueError, match="loopback"):
        create_loopback_server(app, host="0.0.0.0", port=0)


def test_loopback_serves_the_same_built_component_to_the_exact_storyforge_origin(
    tmp_path,
) -> None:
    root, bundle = sealed_plugin(tmp_path)
    launch = create_dashboard_loopback_app(
        service(tmp_path),
        plugin_root=root,
        storyforge_origin="http://127.0.0.1:5173",
    )
    app = launch.app

    status, headers, body = call_app(
        app, path="/component.js", session=None, csrf=None
    )
    assert status == 200
    assert headers["Content-Type"] == "text/javascript; charset=utf-8"
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert body == bundle


@pytest.mark.parametrize(
    "origin",
    ["null", "*", "file://local", "http://user:pass@127.0.0.1:5173", "http://127.0.0.1:5173/path"],
)
def test_loopback_rejects_unsafe_origin_configuration(tmp_path, origin: str) -> None:
    root, _ = sealed_plugin(tmp_path)
    with pytest.raises(ValueError, match="origin"):
        create_dashboard_loopback_app(
            service(tmp_path),
            plugin_root=root,
            storyforge_origin=origin,
        )


def test_loopback_generated_capabilities_are_distinct_and_nontrivial(tmp_path) -> None:
    root, _ = sealed_plugin(tmp_path)
    launch = create_dashboard_loopback_app(
        service(tmp_path),
        plugin_root=root,
        storyforge_origin="http://127.0.0.1:5173",
    )

    assert len(launch.session_token) >= 32
    assert len(launch.csrf_token) >= 32
    assert launch.session_token != launch.csrf_token
