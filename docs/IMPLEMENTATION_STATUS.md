# Writing Ops Implementation Status

All durable outputs in this ledger have `human_review_status: pending` until the user explicitly accepts or rejects them.

| Milestone | State | Independent review | Human review | CommitSet | Next |
| --- | --- | --- | --- | --- | --- |
| M0 Host probe | completed | passed | pending | revision 3 frozen | Continue M1; await optional human review |
| M1 Core contracts | completed | revision 6 failed; exceptional remediation explicitly waived | approved | remediation revision 7 frozen | Begin M2 |
| M2 Dashboard and Trace | in progress | pending | pending | pending | Determine current code/test state, then enter strict RED for the shared ViewModel |
| M3 PlotRail materialization | pending | pending | pending | pending | Wait for M2 review |
| M4 Runtime and browser | pending | pending | pending | pending | Wait for M3 review |
| M5 Review and CAS adoption | pending | pending | pending | pending | Wait for M4 review |
| M6 Real unattended acceptance | pending | pending | pending | pending | Wait for M5 review |

## Active execution

- Automation: `writing-ops` (`推进 Writing Ops 工程实施`), active, two-minute heartbeat.
- Execution mode: project-bound SkillFlow protocol at `.agents/skills/writing-ops-plan/SKILL.md`.
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

The fresh independent review verified both authorized findings closed, but found one additional Important issue: legacy or direct-SQL approval rows can contain an invalid timezone or malformed/non-aware expiry, causing approval validation or consumption to raise instead of fail closed. The user subsequently resumed the task and authorized completion.

The bounded repair now uses one approval-time parser at API, SQLite-trigger, migration-validation, and runtime-validation boundaries. Invalid IANA timezones, malformed timestamps, and timezone-naive timestamps fail closed; damaged legacy rows return `approval_time_invalid` and cannot be consumed. The full local machine gate passed: 21 Python tests, Ruff, Vitest, TypeScript, Vite build, and plugin validation. A new CommitSet and fresh independent review are still required before M1 can complete.

Revision 5 independent review confirmed that time-integrity repair closed, but found two Important SQLite replacement-semantics gaps: `INSERT OR REPLACE` could replace an existing goal revision because recursive delete triggers were disabled, and a same-ID approval could be replaced or deleted. M1 remains in repair and M2 remains gated.

The replacement-semantics repair enables recursive SQLite triggers, rejects duplicate revision keys before INSERT for every goal level, rejects duplicate approval IDs before INSERT, and makes approval DELETE immutable. Adversarial tests prove `INSERT OR REPLACE` cannot change goal hashes or reset/replace/delete an approval. The full local machine gate passed: 22 Python tests, Ruff, Vitest, TypeScript, Vite build, and plugin validation. A new CommitSet and fresh independent review remain required.

Revision 6 independent review verified the frozen package and installed build but failed M1 with
three Important findings and one Minor evidence-scope finding:

1. `M1-APPROVAL-ID-IMMUTABLE`: direct SQL can rename an approval primary key and reuse the old ID.
2. `M1-APPROVAL-LIFECYCLE-ONEWAY`: direct SQL can clear `consumed_at`, while runtime validation
   ignores `invalidated_reason`.
3. `M1-MIGRATION-FAILURE-ATOMIC`: migrations commit schema/version changes before legacy validation,
   so a failed migration is not failure-atomic.
4. `M1-EVIDENCE-SCOPE-R6` (Minor): regression evidence does not cover those three paths.

The ordinary M1 independent-review budget is exhausted. The user approved a structural recovery:
this file is now the unique status source, the implementation plan is isolated in
`docs/IMPLEMENTATION_PLAN.md`, and the generated project protocol must route the three findings as
an explicit remediation block rather than silently labeling the next adjudication a seventh ordinary
review. M2 remains gated.

The generated project protocol at `.agents/skills/writing-ops-plan/SKILL.md` is source-bound to plan
revision `2026-09-01-r1` and the active SkillFlow manifest. Its deterministic RED/GREEN fixtures,
frontmatter parse, source-identity check, Python/UI gates, and minimum recovery smoke passed. This
establishes a draft project protocol; host discovery and a real governed task are not yet claimed.

The M1 remediation now has fresh failing-first evidence and GREEN implementation for all three
Important findings. Approval primary keys reject direct-SQL renaming; consumed and invalidated
lifecycle values are one-way; runtime validation honors `invalidated_reason`; and failed migration
validation restores the pre-migration SQLite schema and data from a consistent backup. The complete
machine gate passed with 31 Python tests and one existing dependency warning, Ruff, the UI test,
TypeScript, and Vite build. Distribution reseal/install/smoke and the remediation CommitSet remain
pending; this is not yet human acceptance or M1 completion.

The remediation implementation is committed at `cc4d84973ee2379bf21e74c8d839d7e85f6e34cb`.
Materialized plugin validation, reseal, installation, and installed-cache smoke passed for
`0.1.0+codex.20260902093510` / `sha256:1906bf9c8ce1b44b136018d842515e52eae7191e153cee48bd6d46b6a2dde8be`.
CommitSet M1 revision 7 freezes the candidate and review package digest
`cf08af51946bf5e211b38549d3f7ae8eefee2e05a68f009ce7871e41f5097e5e`.
Before user adjudication, the ordinary review ceiling was exhausted, so no new independent reviewer
was dispatched and the protocol required an explicit human decision. At that point M1 remained
incomplete and M2 had not started.

The user selected adjudication option 1 and approved CommitSet M1 revision 7. HumanReview record
`human-m1-remediation-r7` binds the approval to subject `M1:7`; the waiver of a new independent
review is limited to this exceptional remediation. M1 is therefore complete. M0 remains pending
optional human review, and M2-M6 retain their normal independent-review requirements.

## M2 active work

- ExecutionLease `writing-ops-engineering` is held for milestone M2 by this thread with worker
  fingerprint `codex-root-m2`; the two-minute heartbeat must not dispatch competing work while the
  lease remains valid.
- Current route: classify the existing dashboard/trace implementation against fresh code and test
  anchors, then start the earliest missing executable behavior with strict RED evidence.
- Shared ViewModel sub-gate: schema v2 now reads the real immutable long-term, cycle, and daily goal
  revisions from SQLite; the same object drives the structured MCP result and text renderer. The
  React renderer exposes creator/reviewer mode switching and renders those real goal payloads.
- Failing-first evidence was observed separately for the missing server ViewModel and missing React
  mode switch. The post-change full gate passed with 32 Python tests (one existing dependency
  warning), Ruff, 2 UI tests, TypeScript, and Vite build.
- Next route: implement allowlisted hash-chained Trace, atomic Artifact storage, CommitSet/review
  projections, then surface them through the reviewer ViewModel before adding the Storyforge
  owner-only fallback.
- No M2 completion, CommitSet, independent review, or human acceptance is claimed yet.
