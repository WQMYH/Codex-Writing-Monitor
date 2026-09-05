from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlencode, urlsplit
from wsgiref.simple_server import WSGIServer, make_server

from writing_ops.materialize import verify_bundle
from writing_ops.service import WritingOpsService

StartResponse = Callable[[str, list[tuple[str, str]]], None]
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


def validate_storyforge_origin(value: str) -> str:
    if value in {"null", "*"}:
        raise ValueError("Storyforge origin must be a concrete http/https origin")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Storyforge origin must be a concrete http/https origin")
    canonical = f"{parsed.scheme}://{parsed.netloc}"
    if value != canonical:
        raise ValueError("Storyforge origin must be canonical")
    return canonical


def validate_generated_capability_tokens(session_token: str, csrf_token: str) -> None:
    if (
        not TOKEN_PATTERN.fullmatch(session_token)
        or not TOKEN_PATTERN.fullmatch(csrf_token)
        or secrets.compare_digest(session_token, csrf_token)
    ):
        raise ValueError("loopback session and CSRF tokens must be strong and distinct")


def load_verified_ui_component(plugin_root: Path) -> bytes:
    root = plugin_root.resolve(strict=True)
    verify_bundle(root)
    component = root / "ui" / "dist" / "component.js"
    if not component.is_file():
        raise ValueError("sealed plugin does not contain ui/dist/component.js")
    return component.read_bytes()


class _DashboardLoopbackApp:
    """Owner-only WSGI projection created only from a sealed plugin root."""

    def __init__(
        self,
        service: WritingOpsService,
        *,
        storyforge_origin: str,
        session_token: str,
        csrf_token: str,
        component: bytes,
    ) -> None:
        self._service = service
        self._storyforge_origin = storyforge_origin
        self._session_token = session_token
        self._csrf_token = csrf_token
        self._component = component

    def __call__(
        self, environ: dict[str, Any], start_response: StartResponse
    ) -> Iterable[bytes]:
        origin = str(environ.get("HTTP_ORIGIN", ""))
        if not secrets.compare_digest(origin, self._storyforge_origin):
            return self._respond(start_response, 403, {"error": "origin_not_allowed"})

        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if method == "OPTIONS":
            headers = self._cors_headers()
            if environ.get("HTTP_ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK") == "true":
                headers.append(("Access-Control-Allow-Private-Network", "true"))
            start_response("204 No Content", headers)
            return [b""]
        if method != "GET":
            return self._respond(start_response, 405, {"error": "method_not_allowed"})
        if environ.get("PATH_INFO") == "/component.js":
            start_response(
                "200 OK",
                self._cors_headers()
                + [
                    ("Content-Type", "text/javascript; charset=utf-8"),
                    ("Content-Length", str(len(self._component))),
                ],
            )
            return [self._component]
        if environ.get("PATH_INFO") != "/api/writing-ops/dashboard":
            return self._respond(start_response, 404, {"error": "not_found"})
        if not secrets.compare_digest(
            str(environ.get("HTTP_X_WRITING_OPS_SESSION", "")), self._session_token
        ):
            return self._respond(start_response, 401, {"error": "session_required"})
        if not secrets.compare_digest(
            str(environ.get("HTTP_X_WRITING_OPS_CSRF", "")), self._csrf_token
        ):
            return self._respond(start_response, 403, {"error": "csrf_required"})
        return self._respond(
            start_response,
            200,
            self._service.dashboard().model_dump(mode="json"),
        )

    def _cors_headers(self) -> list[tuple[str, str]]:
        return [
            ("Access-Control-Allow-Origin", self._storyforge_origin),
            ("Access-Control-Allow-Methods", "GET, OPTIONS"),
            (
                "Access-Control-Allow-Headers",
                "X-Writing-Ops-Session, X-Writing-Ops-CSRF",
            ),
            ("Vary", "Origin"),
            ("Cache-Control", "no-store"),
        ]

    def _respond(
        self, start_response: StartResponse, status: int, payload: dict[str, Any]
    ) -> list[bytes]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        reasons = {
            200: "OK",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            405: "Method Not Allowed",
        }
        headers = self._cors_headers() + [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ]
        start_response(f"{status} {reasons[status]}", headers)
        return [body]


@dataclass(frozen=True, slots=True)
class DashboardLoopbackLaunch:
    app: _DashboardLoopbackApp
    session_token: str
    csrf_token: str


@dataclass(slots=True)
class DashboardLoopbackRuntime:
    server: WSGIServer
    thread: Thread
    dashboard_endpoint: str
    storyforge_url: str
    session_token: str
    csrf_token: str

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def create_dashboard_loopback_app(
    service: WritingOpsService,
    *,
    plugin_root: Path,
    storyforge_origin: str,
) -> DashboardLoopbackLaunch:
    origin = validate_storyforge_origin(storyforge_origin)
    session = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    validate_generated_capability_tokens(session, csrf)
    return DashboardLoopbackLaunch(
        app=_DashboardLoopbackApp(
            service,
            storyforge_origin=origin,
            session_token=session,
            csrf_token=csrf,
            component=load_verified_ui_component(plugin_root),
        ),
        session_token=session,
        csrf_token=csrf,
    )


def create_loopback_server(
    app: _DashboardLoopbackApp, *, host: str = "127.0.0.1", port: int = 0
) -> WSGIServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("dashboard server must bind to a loopback host")
    return make_server(host, port, app)


def start_dashboard_loopback(
    service: WritingOpsService,
    *,
    plugin_root: Path,
    storyforge_origin: str,
) -> DashboardLoopbackRuntime:
    launch = create_dashboard_loopback_app(
        service, plugin_root=plugin_root, storyforge_origin=storyforge_origin
    )
    server = create_loopback_server(launch.app)
    endpoint = f"http://127.0.0.1:{server.server_port}/api/writing-ops/dashboard"
    fragment = urlencode(
        {
            "endpoint": endpoint,
            "session": launch.session_token,
            "csrf": launch.csrf_token,
            "mount": "writing-ops-root",
        }
    )
    thread = Thread(target=server.serve_forever, name="writing-ops-loopback", daemon=True)
    thread.start()
    return DashboardLoopbackRuntime(
        server=server,
        thread=thread,
        dashboard_endpoint=endpoint,
        storyforge_url=f"{validate_storyforge_origin(storyforge_origin)}/writing-ops#{fragment}",
        session_token=launch.session_token,
        csrf_token=launch.csrf_token,
    )
