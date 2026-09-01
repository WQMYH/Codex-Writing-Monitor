# Writing Ops Implementation Status

All durable outputs in this ledger have `human_review_status: pending` until the user explicitly accepts or rejects them.

| Milestone | State | Independent review | Human review | CommitSet | Next |
| --- | --- | --- | --- | --- | --- |
| M0 Host probe | completed | passed | pending | revision 3 frozen | Continue M1; await optional human review |
| M1 Core contracts | review_ready | exceptional third repair implemented; review pending | pending | revision 4 frozen | Run fresh independent review |
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
- SQLite migration creates all approved core tables, validates legacy rows fail-closed, and remains separate from plugin cache.
- Long-term, cycle, and daily goals append immutable revisions with canonical payload hashes.
- Daily approvals require the complete writing contract, bind all three revisions/hash/timezone/expiry/auto-adopt, invalidate on parent revision or expiry changes, and are consumed with validation in one immediate transaction.
- Run state transitions reject skips and terminal replay.
- ExecutionLease uses `BEGIN IMMEDIATE`, full task/milestone/owner/worker identity, monotonic heartbeat/expiry, safe takeover only after expiry, and full-identity release.
- All external runtime actions use a fake adapter; no Storyforge, Writing MCP, Edge, or browser process is started in M1.

## M1 human block

The final fresh independent review verified the frozen package digest and reported two Important findings after the two permitted automatic repair rounds were exhausted:

1. SQLite still permits replacing an existing goal revision, and parent payload/hash validity is not fail-closed for direct SQL and legacy data.
2. Approval records bind parent revision numbers but not parent IDs, so a same-number parent-chain substitution could remain valid.

M1 and all review outputs remain `human_review_status: pending`. M2 has not started.

The user subsequently authorized an exceptional third repair round. That authorization removes the execution block only for the two findings above; M2 remains gated on fresh machine evidence, a new CommitSet revision, and a new independent review.

The bounded repair now makes every goal revision UPDATE/DELETE-proof at the SQLite boundary, validates parent JSON and canonical hashes on insert and migration, stores both parent IDs in approvals, backfills legacy approvals, and rejects parent identity/revision substitution. The full local machine gate passed: 14 Python tests, Ruff, Vitest, TypeScript, and Vite build.
