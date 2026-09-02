from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from writing_ops.loopback import DashboardLoopbackApp, create_loopback_server
from writing_ops.service import WritingOpsService
from writing_ops.state import StateStore


def call_app(
    app: DashboardLoopbackApp,
    *,
    method: str = "GET",
    path: str = "/api/writing-ops/dashboard",
    origin: str = "http://127.0.0.1:5173",
    session: str | None = "session-test",
    csrf: str | None = "csrf-test",
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


def test_loopback_dashboard_requires_exact_origin_memory_tokens_and_csrf(tmp_path) -> None:
    app = DashboardLoopbackApp(
        service(tmp_path),
        storyforge_origin="http://127.0.0.1:5173",
        session_token="session-test",
        csrf_token="csrf-test",
    )

    status, headers, body = call_app(app)
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert headers["Cache-Control"] == "no-store"
    assert json.loads(body)["schema_version"] == 2
    assert b"session-test" not in body and b"csrf-test" not in body

    assert call_app(app, origin="http://evil.example")[0] == 403
    assert call_app(app, session=None)[0] == 401
    assert call_app(app, csrf=None)[0] == 403
    assert call_app(app, method="POST")[0] == 405


def test_loopback_preflight_is_exact_and_server_cannot_bind_non_loopback(tmp_path) -> None:
    app = DashboardLoopbackApp(
        service(tmp_path),
        storyforge_origin="http://127.0.0.1:5173",
        session_token="session-test",
        csrf_token="csrf-test",
    )

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
