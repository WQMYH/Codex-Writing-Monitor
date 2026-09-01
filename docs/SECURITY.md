# Security Boundary

- Storyforge remains the authority for prose and canon.
- Writing MCP remains read-only.
- The M0 dashboard is read-only and performs no browser or process action.
- Plugin code is installed from a materialized bundle under `.dist/current`.
- Runtime state will live under `%LOCALAPPDATA%\WritingOps`, never in the versioned plugin cache.
- Credentials, cookies, bearer tokens, and pairing codes must never enter Trace artifacts.
- No tool accepts arbitrary shell commands, URLs, selectors, or JavaScript.

