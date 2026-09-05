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
- The M4 runtime session starts the guarded loopback first, passes its one-time Storyforge fragment
  only to the dedicated Edge process, and tears down Edge, Storyforge, and loopback in reverse
  order.
- `writing_runtime_start` and `writing_runtime_stop` are prompt-by-default MCP operations. Start
  reads only `%LOCALAPPDATA%\WritingOps\runtime.json`; absent or invalid configuration blocks
  before Edge lookup or process creation. It never accepts caller-provided launch parameters.
- The browser-use fallback is a separate Python 3.12/uv environment pinned to `0.13.8`. Its only
  current command is version health; it creates no `Agent`, accepts no browsing instruction, and
  is not a second autonomous model.
- Its future Browser Harness daemon receives a fixed `BU_CDP_URL` only for the owned loopback CDP
  Origin and uses a dedicated `BH_HOME`, runtime, temporary, and workspace root under Writing Ops
  state. It never discovers or reuses the user's default browser profile.
- The supervisor starts the daemon only through the isolated worker virtual environment, supplies
  only the owned CDP Origin and runtime root, records its Windows process identity, and closes its
  Job before closing Edge. Runtime status exposes only that PID and `autonomous_agent=false`.
- Dedicated Edge enables CDP only at `127.0.0.1` on a random port. The supervisor accepts the port
  only from its owned profile's `DevToolsActivePort` file; Job setup failure releases that profile
  lock rather than taking over or deleting an unknown owner.
- pairing-code handling remains a separate M4 requirement.
