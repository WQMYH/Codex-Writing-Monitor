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
- Only `GET /api/writing-ops/dashboard`, the exact-Origin `GET /component.js`, and their `OPTIONS`
  preflight are supported. The API exposes the same read-only ViewModel as `writing_dashboard` and
  is not a second state service. The component resource contains only the built dashboard code; it
  contains no state or launch secret.
- CORS uses one exact configured Storyforge Origin, never `*`. Private Network Access is acknowledged
  only for a valid preflight from that exact Origin.
- Every dashboard read requires separate in-memory `X-Writing-Ops-Session` and
  `X-Writing-Ops-CSRF` values. Responses are `no-store`; tokens are never returned in response
  bodies or persisted in Trace.
- Storyforge receives the fixed endpoint, session token, CSRF token, and fixed mount ID in a
  one-time URL fragment. Fragments are not sent in HTTP requests or referrers. The shared component
  validates the fixed loopback path and mount, removes the fragment with `history.replaceState`
  during initialization, and retains the tokens only in memory.
- Storyforge's internal `/writing-ops` route (under its configured router basename) is only a mount
  shell. It loads the exact-Origin `/component.js`; it does not copy the component or read Writing
  Ops persistence directly.
- M2 provides the guarded application and loopback-only server factory but does not automatically
  start a port or compose the launch URL. Lifecycle ownership and process supervision remain gated
  on M4.

## Runtime supervision boundary

- The Storyforge launcher accepts only a `RuntimeConfiguration` produced by the verified local
  configuration loader; no MCP tool accepts a command, working directory, URL, selector, or
  JavaScript input.
- A child receives only the supervisor's explicit Windows environment allowlist plus its
  supervisor nonce. It does not inherit arbitrary parent environment variables.
- Every launched child is assigned to a Windows Job Object and recorded with its PID, creation
  time, and configuration fingerprint. Closing that owned Job terminates only its managed child.
- The launcher is not yet wired to an MCP start operation; browser-use and pairing-code handling
  remain separate M4 requirements.
