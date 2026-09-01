# Writing Ops Implementation Status

All durable outputs in this ledger have `human_review_status: pending` until the user explicitly accepts or rejects them.

| Milestone | State | Independent review | Human review | CommitSet | Next |
| --- | --- | --- | --- | --- | --- |
| M0 Host probe | completed | passed | pending | revision 3 frozen | Continue M1; await optional human review |
| M1 Core contracts | review_ready | failed (repair round 1) | pending | revision 1 frozen | Re-run gates and independent repair review |
| M2 Dashboard and Trace | pending | pending | pending | pending | Wait for M1 review |
| M3 PlotRail materialization | pending | pending | pending | pending | Wait for M2 review |
| M4 Runtime and browser | pending | pending | pending | pending | Wait for M3 review |
| M5 Review and CAS adoption | pending | pending | pending | pending | Wait for M4 review |
| M6 Real unattended acceptance | pending | pending | pending | pending | Wait for M5 review |

## Active execution

- Automation: `writing-ops` (`推进 Writing Ops 工程实施`), active, two-minute heartbeat.
- Execution mode: SkillFlow inline implementation with a fresh independent reviewer at every milestone.
- Git branch: `feat/writing-ops-v1`.
- Installed probe identity is returned at runtime as both the cachebuster version and a SHA-256 build identifier; the frozen CommitSet records the exact installed version.
- Verified M0 surface: cached stdio MCP, `writing_dashboard`, structured text fallback, app resource discovery, fixed dashboard task, and scheduled-task plugin visibility.
- Honest limitation: the current Codex host did not expose enough evidence to prove that the MCP Apps React component rendered; M0 therefore supports the text renderer and records component rendering as unverified. An existing task remains bound to the plugin snapshot it was created with, so installation upgrades require a replacement/reloaded fixed task.
- Runtime support claim: none yet; M0 does not start Storyforge, Edge, browser-use, or a writing run.
- Distribution integrity rule: cachebuster mutation must be followed by bundle resealing; installed-cache smoke rejects any listed file hash or size mismatch before launching MCP.

## M1 evidence

- Stable state root: `%LOCALAPPDATA%\WritingOps` (test override: `WRITING_OPS_DATA_ROOT`).
- SQLite migration creates all approved core tables and remains separate from plugin cache.
- Long-term, cycle, and daily goals append immutable revisions with canonical payload hashes.
- Daily approvals require the complete writing contract, bind all three revisions/hash/timezone/expiry/auto-adopt, and invalidate on parent revision or expiry changes.
- Run state transitions reject skips and terminal replay.
- ExecutionLease uses `BEGIN IMMEDIATE`, owner run IDs, worker fingerprints, heartbeat/expiry, safe takeover only after expiry, and owner-bound release.
- All external runtime actions use a fake adapter; no Storyforge, Writing MCP, Edge, or browser process is started in M1.
