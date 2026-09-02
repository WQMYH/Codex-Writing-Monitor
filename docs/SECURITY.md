# Security Boundary

- Storyforge remains the authority for prose and canon.
- Writing MCP remains read-only.
- The M0 dashboard is read-only and performs no browser or process action.
- Plugin code is installed from a materialized bundle under `.dist/current`.
- Runtime state will live under `%LOCALAPPDATA%\WritingOps`, never in the versioned plugin cache.
- Credentials, cookies, bearer tokens, and pairing codes must never enter Trace artifacts.
- No tool accepts arbitrary shell commands, URLs, selectors, or JavaScript.

## Storyforge fallback loopback boundary

- The dashboard fallback API is owner-only and may bind only to `127.0.0.1`, `::1`, or
  `localhost`; wildcard and LAN interfaces are rejected before socket creation.
- Only `GET /api/writing-ops/dashboard` and its `OPTIONS` preflight are supported. The API exposes
  the same read-only ViewModel as `writing_dashboard` and is not a second state service.
- CORS uses one exact configured Storyforge Origin, never `*`. Private Network Access is acknowledged
  only for a valid preflight from that exact Origin.
- Every dashboard read requires separate in-memory `X-Writing-Ops-Session` and
  `X-Writing-Ops-CSRF` values. Responses are `no-store`; tokens are never returned in response
  bodies or persisted in Trace.
- M2 provides the guarded application and loopback-only server factory but does not automatically
  start a port. Lifecycle ownership and process supervision remain gated on M4.
