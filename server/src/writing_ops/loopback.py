from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from wsgiref.simple_server import WSGIServer, make_server

from writing_ops.service import WritingOpsService

StartResponse = Callable[[str, list[tuple[str, str]]], None]


class DashboardLoopbackApp:
    """Owner-only WSGI projection for the Storyforge fallback renderer."""

    def __init__(
        self,
        service: WritingOpsService,
        *,
        storyforge_origin: str,
        session_token: str | None = None,
        csrf_token: str | None = None,
        ui_bundle_path: Path | None = None,
    ) -> None:
        self._service = service
        self._storyforge_origin = storyforge_origin
        self._session_token = session_token or secrets.token_urlsafe(32)
        self._csrf_token = csrf_token or secrets.token_urlsafe(32)
        self._ui_bundle_path = ui_bundle_path

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
            if self._ui_bundle_path is None or not self._ui_bundle_path.is_file():
                return self._respond(start_response, 404, {"error": "component_not_found"})
            body = self._ui_bundle_path.read_bytes()
            start_response(
                "200 OK",
                self._cors_headers()
                + [
                    ("Content-Type", "text/javascript; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]
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


def create_loopback_server(
    app: DashboardLoopbackApp, *, host: str = "127.0.0.1", port: int = 0
) -> WSGIServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("dashboard server must bind to a loopback host")
    return make_server(host, port, app)
