# Writing Ops Implementation Status

All durable outputs in this ledger have `human_review_status: pending` until the user explicitly accepts or rejects them.

| Milestone | State | Independent review | Human review | CommitSet | Next |
| --- | --- | --- | --- | --- | --- |
| M0 Host probe | completed | passed | pending | revision 3 frozen | Continue M1; await optional human review |
| M1 Core contracts | completed | revision 6 failed; exceptional remediation explicitly waived | approved | remediation revision 7 frozen | Begin M2 |
| M2 Dashboard and review projection | completed; usable delivery installed | revision 4 passed_with_findings | pending | revision 4 frozen | Begin M3; M4/M5 work remains separate |
| M3 PlotRail materialization | completed; installed | revision 3 passed_with_findings | pending | revision 3 frozen | Begin M4; retain test-coverage finding |
| M4 Runtime and browser | completed; installed runtime candidate | passed (r4) | pending | revision 4 frozen | Begin M5; retain explicit human review |
| M5 Review and CAS adoption | in progress; checkpoint 4 run-binding repair awaits re-review | checkpoint 4 failed P1; repair pending re-review | pending | pending | Re-review run binding, then add claim/token handoff |
| M6 Real unattended acceptance | pending | pending | pending | pending | Wait for M5 review |

## Active execution

- Automation: `writing-ops` (`推进 Writing Ops 工程实施`), active, two-minute heartbeat.

## M5 checkpoint 1 (2026-09-08)

- Safe UTF-8 candidate/review/JSON artifacts now use a generated allowlisted path, temporary-file
  flush, atomic replacement, SHA-256 registration, and a SQLite transaction. An unknown Run is
  rejected before creating an artifact; security screenshots remain fail-closed.
- Allowlisted Trace payloads are normalized before persistence, use per-Run sequence/hash chaining,
  and reject an unknown Run. Artifact and Trace rows remain `human_review_status=pending`.
- Focused evidence passed: `server/tests/test_dashboard_viewmodel.py` (16 passed) and focused Ruff.
  No real writing artifact, Storyforge adoption, Codex submission, browser worker, or external
  runtime was started. GateReceipt, bounded review, and CAS adoption remain unimplemented.

## M5 checkpoint 2 (2026-09-08)

- GateReceipt now binds the frozen ReviewPacket/candidate/context hashes, configured model and task
  identifiers, prompt/input/output hashes, deterministic checks, required semantic dimensions,
  findings, and revision count. The reviewer view and text fallback display its verified status.
- A `passed` receipt requires every deterministic and required semantic check to pass, no P0/P1,
  and no P2 tied to a required dimension. `uncertain` can only be stored as `blocked`; it cannot
  authorize adoption. All receipts remain `human_review_status=pending`.
- Focused evidence passed: 20 Python tests, focused Ruff, 4 UI tests, and TypeScript typecheck.
  The related complete service/UI gate also passed: 83 Python tests, full Ruff, and UI production
  build (two pre-existing Rollup/Zod pure-comment warnings). This is local receipt persistence
  only; Codex verdict dispatch, revision, and Storyforge CAS are still unimplemented.

## M5 checkpoint 3 (2026-09-08)

- A ReviewPacket is now re-hashed before its structured verdict can produce a GateReceipt payload.
  Candidate/context/input/output hashes are derived from the verified packet and normalized verdict;
  the configured model is recorded without claiming an observed model.
- The gate status is deterministic rather than model-controlled. A changed packet fails closed before
  receipt persistence. Focused ReviewPacket tests and Ruff passed; the broader pytest suite could
  not start because the current restricted environment cannot remove a pre-existing `.pytest-tmp`.
- The output is still a local, pending-review payload. No Codex dispatch, revision, or Storyforge
  adoption is claimed.

## M5 checkpoint 4 (2026-09-12)

- `WritingOpsService.record_review_verdict` is now the single internal path from a verified
  ReviewPacket and structured verdict to a persisted GateReceipt. It reuses the existing packet
  hash verification and deterministic gate calculation before the StateStore transaction.
- One runtime-status test now injects its SQLite store instead of touching the default user data
  directory. This closes the restricted-environment test isolation failure without changing the
  production storage path or deleting prior evidence.
- Evidence passed on the current worktree: 3 focused ReviewPacket tests, 88 complete Python tests
  with one pre-existing Pydantic warning, and full Ruff. All outputs remain
  `human_review_status=pending`.
- The service method is not yet exposed through `writing_run_due`: durable claim/resume-token
  validation, bounded revision, real Codex handoff, and Storyforge CAS remain unimplemented. No
  external runtime, writing action, or adoption was started.

### M5 checkpoint 4 independent review block and repair candidate (2026-09-12)

- Independent review `01a094b3-2bc2-7ed1-9d94-d8f093416187` failed checkpoint 4 with P1:
  a valid ReviewPacket for one Run could be persisted as a passed/verified GateReceipt for another
  existing Run. The earlier machine pass did not close that ownership boundary.
- The bounded repair binds `run_id` into the frozen ReviewPacket hashes and GateReceipt payload,
  verifies the packet binding before receipt construction, and rechecks the receipt binding inside
  the existing StateStore write transaction. Legacy receipts without this binding are explicitly
  rejected instead of being silently upgraded to verified.
- Five focused binding regressions and full Ruff passed. The complete Python gate passed with 89
  tests and one pre-existing Pydantic warning. Cross-Run mismatch and Run-id tampering fail before
  persistence; the correct Run still succeeds.
- This is a repair candidate, not a review pass. It remains `human_review_status=pending` and awaits
  the same independent review before checkpoint 4 can close. No MCP exposure, installation, push,
  external runtime, Codex dispatch, revision, or Storyforge adoption occurred.
- Execution mode: project-bound SkillFlow protocol at `.agents/skills/writing-ops-plan/SKILL.md`.
- Git branch: `feat/writing-ops-v1`.
- Installed probe identity is returned at runtime as both the cachebuster version and a SHA-256 build identifier; the frozen CommitSet records the exact installed version.
- Verified M0 surface: cached stdio MCP, `writing_dashboard`, structured text fallback, app resource discovery, fixed dashboard task, and scheduled-task plugin visibility.
- Honest limitation: the current Codex host did not expose enough evidence to prove that the MCP Apps React component rendered; M0 therefore supports the text renderer and records component rendering as unverified. An existing task remains bound to the plugin snapshot it was created with, so installation upgrades require a replacement/reloaded fixed task.
- Runtime support claim: none yet; M0 does not start Storyforge, Edge, browser-use, or a writing run.
- Distribution integrity rule: cachebuster mutation must be followed by bundle resealing; installed-cache smoke rejects any listed file hash or size mismatch before launching MCP.

## M4 checkpoint 1 (2026-09-05)

- The first M4 TDD checkpoint defines a launch specification only: it requires an existing
  `msedge.exe`, derives a dedicated `%LOCALAPPDATA%\\WritingOps` profile and profile-lock path,
  and reuses the exact canonical Storyforge Origin validation. It rejects another executable name
  and non-canonical Origin input before a process can be started.
- No directory, lock, listener, Edge process, browser-use worker, pairing code, Storyforge runtime,
  or Writing MCP runtime is created by this checkpoint.
- Focused test, full Python suite (59 passed; one pre-existing Pydantic warning), Ruff, UI tests
  (4 passed), TypeScript, and production build passed. The Vite build retained its two pre-existing
  Rollup/Zod pure-comment warnings. This is an in-progress machine-gate checkpoint, not an M4
  completion claim; all outputs remain `human_review_status=pending`.

## M4 checkpoint 2 (2026-09-05)

- The Edge profile lock now uses atomic exclusive creation. A pre-existing lock is reported as a
  conflict and its owner marker is left intact; this checkpoint never deletes, takes over, or
  terminates an unknown owner.
- Focused tests and the complete gate set passed: 60 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 checkpoint 3 (2026-09-05)

- Profile-lock release now requires the same supervisor nonce that acquired it. A missing lock or
  nonce mismatch fails closed, leaving any existing lock untouched.
- Focused tests and the complete gate set passed: 61 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 checkpoint 4 (2026-09-05)

- The guarded loopback factory now has an explicit lifecycle: it binds only `127.0.0.1` on an
  ephemeral port, serves in a daemon thread, composes the existing fixed Storyforge
  `/writing-ops` one-shot fragment, and exposes explicit shutdown. Tokens remain in memory and
  appear only in the URL fragment, never in the endpoint query.
- Focused tests and the complete gate set passed: 62 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 checkpoint 5 (2026-09-05)

- Windows supervision now records a process identity as PID plus native creation time and rejects a
  same-PID identity with a different creation time. This is read-only identity evidence; it starts,
  stops, and attaches to no process.
- Focused tests and the complete gate set passed: 63 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 checkpoint 6 (2026-09-05)

- The runtime configuration now accepts only a JSON object containing a verified Storyforge root
  and exact Storyforge Origin. The root must identify the local `storyforge` package with its fixed
  writing-bridge `npm run dev` entry; any other command field or dev entry is rejected before
  process launch.
- Focused tests and the complete gate set passed: 64 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 checkpoint 7 (2026-09-05)

- The Windows supervisor now has a native Job Object wrapper. It sets the kill-on-close limit,
  assigns only a process opened with the required Windows rights, and explicitly terminates the
  owned Job before closing its handle. A controlled Python child confirms the lifecycle; no
  existing Edge, Storyforge, or user process is inspected, attached, or stopped.
- Focused tests and the complete gate set passed: 65 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 checkpoint 8 (2026-09-05)

- A verified runtime configuration now carries the SHA-256 fingerprint of the exact JSON bytes
  that supplied its Storyforge root and Origin. Later launch and reconciliation code can bind a
  process record to that configuration instead of treating a verified root as timeless.
- Focused tests and the complete gate set passed: 65 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 checkpoint 9 (2026-09-05)

- The dedicated Edge command now accepts a handoff only when it is the configured Storyforge
  Origin's `/writing-ops` route, contains a fragment, and contains no query parameters. Arbitrary
  destinations and query-carried capability values are rejected before process creation.
- Focused tests and the complete gate set passed: 65 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 checkpoint 10 (2026-09-05)

- The verified Storyforge configuration can now launch one owned Windows child through a Job
  Object. The launcher records its PID/creation-time identity and configuration fingerprint,
  suppresses inherited non-allowlisted environment variables, and closes the owned child through
  the Job. The regression uses a disposable Python process; no actual Storyforge or Edge runtime
  was started, and no MCP start tool is wired yet.
- Focused tests and the complete gate set passed: 66 Python tests (one pre-existing Pydantic
  warning), Ruff, 4 UI tests, TypeScript, and production build (two pre-existing Rollup/Zod
  pure-comment warnings). M4 remains in progress and all outputs remain
  `human_review_status=pending`.

## M4 supervised runtime-chain subgate (2026-09-05)

- One internal runtime session now composes guarded loopback, verified Storyforge launch, and
  dedicated Edge launch. Its controlled integration regression proves the one-time handoff reaches
  only the configured Storyforge route, records both process identities, and tears down Edge,
  Storyforge, loopback, and the Edge profile lock in reverse order. It does not start a real
  runtime and is not yet exposed through MCP.
- The complete gate set passed: 68 Python tests (one pre-existing Pydantic warning), Ruff, 4 UI
  tests, TypeScript, and production build (two pre-existing Rollup/Zod pure-comment warnings).
  M4 remains in progress and all outputs remain `human_review_status=pending`.

## M4 MCP runtime-control subgate (2026-09-05)

- `writing_runtime_start` now accepts no launch arguments: it reads only the fixed local
  `runtime.json`, validates the Storyforge root and Origin, resolves a registered/local Microsoft
  Edge executable, then passes that closed configuration to the supervised session. Missing or
  invalid configuration returns a fail-closed, pending-human-review status before launch.
- `writing_runtime_stop` closes only the in-memory session owned by this MCP process. The status
  projection exposes loopback state, owned PIDs, and the configuration fingerprint, never the
  handoff fragment or capability values. browser-use, pairing-code capture, and reconciliation
  remain M4 work.

## M4 browser-worker subgate (2026-09-05)

- An isolated Python 3.12/uv project pins `browser-use==0.13.8`; its locked health command verifies
  the exact installed distribution and reports `autonomous_agent=false`. It does not import or
  create a browser-use `Agent`, launch Edge, attach through CDP, or receive browsing actions.
- This is the bounded fallback foundation only. A future controlled CDP route must be separately
  proved before the worker can inspect or act on the dedicated Edge instance.

## M4 dedicated-Edge CDP subgate (2026-09-05)

- Dedicated Edge now enables remote debugging only on `127.0.0.1` with a random port. The
  supervisor reads the port only from the profile it owns, rejects missing or invalid publication,
  and retains its resulting loopback-only CDP Origin in the managed Edge record.
- If Job Object initialization fails after profile-lock acquisition, the same supervisor nonce
  releases that lock. No existing process is terminated, and no browser-use action is yet allowed.

## M4 browser-harness isolation subgate (2026-09-05)

- The fallback worker now derives Browser Harness environment only from the owned loopback CDP
  Origin and Writing Ops runtime root: `BU_CDP_URL`, daemon name, home, runtime, temporary, and
  workspace locations are all explicit. Default browser discovery and user-profile reuse are not
  part of this route.
- The daemon is still not launched. Its Job ownership, no-secret environment inheritance, and
  stop/reconciliation behavior remain prerequisites for a later M4 worker-connect subgate.

## M4 browser-harness lifecycle subgate (2026-09-05)

- The isolated worker now has one supervised `--daemon` entry. It derives Browser Harness settings
  solely from the supervisor-provided loopback CDP Origin and Writing Ops runtime root; it cannot
  accept a user profile, URL, selector, or model task.
- The runtime session owns the daemon through its own Windows Job, records its PID/creation-time
  identity, projects it as a non-autonomous worker, and tears it down before Edge. Controlled
  child-process tests verify the whitelist and reverse cleanup; no real Storyforge, Edge, or
  browser daemon was started during this checkpoint.

## M4 browser-worker health subgate (2026-09-05)

- Before launching its daemon, the supervisor invokes the worker's fixed `--health` command and
  requires its exact pinned `browser-use==0.13.8`, ready, non-autonomous report. Malformed,
  mismatched, or failing output blocks before a Job or daemon child is created.
- Runtime status projects the verified distribution version with the owned worker PID. Focused
  runtime tests (16 passed), worker tests (3 passed), and focused Ruff passed; no real runtime
  was started. M4 remains in progress and all outputs remain `human_review_status=pending`.

## M4 browser-worker stderr subgate (2026-09-05)

- The daemon's complete stderr is drained as bytes to no artifact, normal log, or status field.
  This keeps an unexpected pairing code out of Trace while preventing a pipe backpressure stall.
  The worker does not expose an auth/login operation, so no pairing flow is enabled.
- Focused runtime tests (16 passed) and focused Ruff passed; no external process was started.
  M4 remains in progress and all outputs remain `human_review_status=pending`.

## M4 runtime reconciliation subgate (2026-09-08)

- `writing_runtime_status` now checks the owned loopback thread and every managed process's PID
  plus creation-time identity. A stopped or mismatched component returns `blocked` with
  `runtime_component_stopped`; it never restarts, replays, or adopts work.
- Focused runtime tests (17 passed) and focused Ruff passed. No external process was started.
  M4 candidate gate and independent review remain pending; all outputs remain
  `human_review_status=pending`.

## M4 revision 1 review block (2026-09-08)

- CommitSet `c8cda323-952d-48e0-a467-a8b201ecd514` freezes Writing Ops
  `098f3155981b7d239668fc4fadcdd10f549bf0d9`, unchanged Storyforge
  `918168323425226772e3d52f6c0abf2bf9673d0a`, unchanged Writing MCP
  `af789429d1b2b4bdc9892d446bcc1b99ef5c0a6c`, and installed build
  `0.1.0+codex.20260908014649` / `sha256:4df4159ca201faf6b24b79eb685cb281ed5da507f06b2c6ccdd95cb943d63712`.
- Fresh independent review `eeb45054-1ba7-4a25-afd7-8796eb554e73` failed with P1
  `M4-RECOVERY-BLOCKED-001` and `M4-STATE-COMMITSET-002`, plus P2
  `M4-EVIDENCE-WORKER-003`. The bounded repair must project preflight failure as blocked, keep the
  authority ledger synchronized, and include the independent worker test in the machine receipt.
  All outputs remain `human_review_status=pending`.

## M4 revision 2/3 repair candidate (2026-09-08)

- Revision 2 CommitSet `634eb9a4-be6d-49f8-98e3-c6c914cae817` was never sent for
  review: its immutable receipt stated review-package size `720` while the
  hashed file was `681` bytes. It remains pending and is invalid for routing;
  it is retained rather than overwritten.
- Revision 3 CommitSet `7ca05178-3b20-4e82-92d5-140f1d237170` correctly freezes
  Writing Ops `6a4dec1528241f91e539494f19d3176457b6eafe`, unchanged Storyforge
  `918168323425226772e3d52f6c0abf2bf9673d0a`, unchanged Writing MCP
  `af789429d1b2b4bdc9892d446bcc1b99ef5c0a6c`, and installed build
  `0.1.0+codex.20260908021022` /
  `sha256:da3d1362cb870db551d8867b35c34ab12bf9317fa0396fe43d15a85bcf1799cc`.
- Revision 3 machine evidence is 81 Python tests, direct worker 3 tests,
  Ruff, UI tests/typecheck/build, materialize/reseal/validation, and actual
  installed-cache MCP smoke. It now awaits a fresh independent review; all
  outputs remain `human_review_status=pending`.

## M4 revision 3/4 review block (2026-09-08)

- Revision 3 fresh review `f0c7a203-9219-4cec-8c48-e7612f7cf46a` failed only
  `M4-RECOVERY-BLOCKED-001`: `subprocess.TimeoutExpired` from worker health was
  outside the service catch set. The repair now catches `SubprocessError` at
  that single launch boundary and has a failing-first timeout regression.
- The same review-recording action exposed a malformed stored findings payload.
  The source state boundary now rejects it for new writes and projects retained
  malformed legacy data as explicit `milestone_review_findings_invalid` /
  `block_now`; no record was overwritten or deleted.
- Revision 4 CommitSet `9b86a9de-26dc-4cbc-a868-e2803fcfcee7` freezes Writing
  Ops `e96410f01ea448d30a804e22de4fd923b60b076b`, unchanged Storyforge
  `918168323425226772e3d52f6c0abf2bf9673d0a`, unchanged Writing MCP
  `af789429d1b2b4bdc9892d446bcc1b99ef5c0a6c`, and installed build
  `0.1.0+codex.20260908033755` /
  `sha256:8434218b13b036273d249121ff9840206a3b5d8bf34c93a783c1f82ec0ef141d`.
  Its 82-Python/3-worker complete machine gate and installed-cache smoke passed;
  its final fresh independent review `ce2c5439-7e6d-415a-8c5f-359d4c2890ad`
  passed. M4 is complete and the installed runtime candidate remains
  `human_review_status=pending`; M5 may begin without implying human acceptance.

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

### Usable delivery slice (2026-09-02)

The implementation route is intentionally narrowed to a usable plugin before additional governance.
The source commits are Writing Ops `0f73bdffc93a1a4de2590e19872eed4f08f78410` and Storyforge
`918168323425226772e3d52f6c0abf2bf9673d0a`. They keep the M2 dashboard, MCP/text fallback, and
Storyforge route, while adding only four delivery-bound fixes: explicit known secret formats cannot
enter artifacts or Trace; browser Trace origins must be canonical HTTP(S) origins; the loopback
factory mints its in-memory capability values; and Storyforge republishes the one-shot handoff
during React StrictMode effect replay.

The installed local snapshot is `writing-ops@gameops-local`
`0.1.0+codex.20260902161346`, build
`sha256:21006e12c562c09f7212279e3a9ea5362fb66d1ee8904d07c4edbcb2589c9606`.
Materialization, resealing, manifest validation, installation, and installed-cache MCP smoke passed:
the complete tool allowlist, structured dashboard, MCP Apps resource, React bundle, and Markdown
fallback are present. All durable results remain `human_review_status=pending`.

This does **not** close full M2 assurance: independent-review findings about external Trace-tail
truncation and a persisted artifact-size claim are deferred to M5 recovery/reconciliation work.
They are not silently marked fixed. Storyforge's focused StrictMode route regression (3 tests) passed;
the plugin server suite (58 tests), plugin UI tests (4), Ruff, and plugin UI production build passed.
The Storyforge monorepo's full production build exceeded the command channel window and is therefore
not claimed as passed.

- ExecutionLease `writing-ops-engineering` is held for milestone M2 by this thread with worker
  fingerprint `codex-root-m2`; the two-minute heartbeat must not dispatch competing work while the
  lease remains valid.
- CommitSet M2 revision 1 is frozen as `a4a8a866-fc08-4f8e-806b-0d159e49d5b7`; independent review
  `0a4dd6d7-b241-4f7e-9576-b59e898a17cb` failed it with 2 Critical, 6 Important, and 1 Minor
  finding. The eight Critical/Important findings block M2 completion; all review output remains
  `human_review_status=pending`.
- Current route: finish the already-started bounded repair against the recorded RED regressions,
  run focused and complete gates, commit both repositories, freeze CommitSet revision 2, and route
  finding closure under the active review policy. The dirty repair candidate is not complete and
  has not been resealed or installed.
- M2 repair round 1 now has current GREEN evidence for all recorded findings plus three boundary
  regressions discovered during pre-commit reconciliation: actual `session=`/`csrf=` launch
  fragments are rejected before persistence, a human-rejected CommitSet cannot be projected as
  completed after an independent pass, and a failed Storyforge component load clears its one-shot
  in-memory handoff.
- The post-repair complete gate passed on the current dirty candidate: 51 Python tests with one
  existing dependency warning, Ruff, 4 UI tests, UI TypeScript, UI production build, Storyforge
  architecture, 115 required tables, generated AI manual, TypeScript, 2 route tests, and production
  build. Commits, reseal/install/smoke, CommitSet revision 2, and review closure remain pending.
- Shared ViewModel sub-gate: schema v2 now reads the real immutable long-term, cycle, and daily goal
  revisions from SQLite; the same object drives the structured MCP result and text renderer. The
  React renderer exposes creator/reviewer mode switching and renders those real goal payloads.
- Failing-first evidence was observed separately for the missing server ViewModel and missing React
  mode switch. The post-change full gate passed with 32 Python tests (one existing dependency
  warning), Ruff, 2 UI tests, TypeScript, and Vite build.
- Next route: implement allowlisted hash-chained Trace, atomic Artifact storage, CommitSet/review
  projections, then surface them through the reviewer ViewModel before adding the Storyforge
  owner-only fallback.
- Artifact/Trace/review sub-gate: artifacts use generated paths, temp-file flush, atomic rename,
  SHA-256, and SQLite registration; Trace accepts only fixed event/field schemas and maintains a
  per-run sequence/hash chain. Artifact, TraceEvent, CommitSet, MilestoneReview, and HumanReview are
  immutable at the SQLite boundary, including `INSERT OR REPLACE` defense for CommitSet.
- Explicit human decisions append an immutable HumanReview and are projected onto the frozen
  subject at read time; the reviewer ViewModel and React/text renderers show CommitSets, verdicts,
  Trace metadata, and current human review without mutating the frozen source row.
- The owner-only fallback API application and loopback-only server factory enforce one exact
  Storyforge Origin, in-memory session/CSRF values, PNA preflight, `no-store`, and GET-only access.
  M2 does not auto-start the port; runtime lifecycle remains gated on M4.
- Post-change full gate passed with 37 Python tests (one existing dependency warning), Ruff, 2 UI
  tests, TypeScript, and Vite build.
- The same built React component now supports MCP Apps and Storyforge loopback bridges. The
  Storyforge bridge accepts only the fixed loopback API, clears its one-time URL fragment during
  initialization, keeps tokens in memory, and fetches with no credentials, no referrer, and
  `no-store`.
- Storyforge commit `7185e469e09d3cf7ade1e30aed07ccd636ca912b` adds the internal
  `/writing-ops` route under the existing router basename. The route is only a fixed mount shell and
  loads the exact-Origin `/component.js`; it does not duplicate the dashboard or access Writing Ops
  state. Storyforge architecture, required-table, generated-manual, TypeScript, 2-test route, and
  production-build gates all passed.
- M2 deliberately does not start the loopback server or compose a launch URL; those lifecycle
  responsibilities remain M4 work.
- Final plugin renderer gate passed with 38 Python tests (one existing dependency warning), Ruff,
  3 UI tests, TypeScript, and Vite production build. Storyforge remained clean at its recorded
  renderer commit after its separate gate.
- Plugin renderer commit `472a9f0353cdab78338c25757e59b01deab4514b` and Storyforge renderer
  commit `7185e469e09d3cf7ade1e30aed07ccd636ca912b` form the tracked candidate.
- A pre-freeze materialized, cachebuster-updated, resealed, validated, installed snapshot passed the
  real installed-cache MCP/resource smoke. The final exact installed version/build belongs in the
  immutable M2 CommitSet and reviewer report so recording it cannot itself change the reviewed Git
  candidate.
- Next route: freeze the M2 review package and exact installed CommitSet, rerun digest-bound
  evidence, and enter the required fresh independent review.
- No M2 completion, CommitSet, independent review, or human acceptance is claimed yet.

### M2 revision 3 review block (2026-09-05)

CommitSet `c75d9b16-e3bd-45c9-9511-98a49a369de3` freezes Writing Ops
`31a75b0bd9edd74db9808bbac069e7c67dd2cf27`, Storyforge
`918168323425226772e3d52f6c0abf2bf9673d0a`, and installed build
`0.1.0+codex.20260905022359` / `sha256:c931f71da3155fdee26563e2134a89615490acb2e2ab3c138171d9cd6fb61e17`.
Its fresh no-history review `b3053123-a46e-4fd3-b362-968876ebfc8b` failed.
All review outputs remain `human_review_status=pending`.

Blocking findings are:

1. `M2-CRIT-001`: finite secret-pattern scanning still permits unlabelled credential prose to reach Artifact temporary-file persistence.
2. `M2-CRIT-002`: free-text Trace `detail` and `result` fields use the same incomplete scan and can persist such credentials.
3. `M2-IMP-003`: the loopback factory mints capabilities, but no production launcher starts the listener or supplies the bootstrap handoff to Storyforge.

`M2-IMP-002` is closed by the current StrictMode regression. `M2-IMP-005` remains explicitly deferred to M5 and is not claimed closed. The full Storyforge production build remains unverified; the focused StrictMode route regression passed.

No automatic fourth repair is permitted. The next human adjudication must choose whether to authorize a bounded M2 remediation for the two Critical persistence boundaries and either wire the loopback launch path now or formally move that requirement to M4. M3-M6 remain blocked.

### M2 revision 4 closure (2026-09-05)

CommitSet `a83dc290-ac9e-4f56-93f2-ac70f7c0e0ab` freezes Writing Ops
`29fb6ec73375ca0a210d5f2cf84b1c1cad0ec129`, unchanged Storyforge
`918168323425226772e3d52f6c0abf2bf9673d0a`, and installed build
`0.1.0+codex.20260905053528` / `sha256:97bed97b6a68be5bd5aac34511c2f41f83094b588ac4edafcad4deb5f6c9155d`.
Its fresh independent review `ef4934a9-a6b5-4690-bfab-9e324f57efd3` passed with one
non-blocking ledger-sync finding. All outputs remain `human_review_status=pending`.

The two persistence findings are closed by removing M2's Artifact and Trace write paths:
both reject all new content before a temporary file or database mutation. This is a
fail-closed delivery boundary, not a secret-pattern claim. M4 owns listener lifecycle and
the one-shot Storyforge handoff; M5 owns redaction, content persistence, atomic recovery,
and Trace-tail recovery. Neither is implemented or claimed by M2.

The r4 independent review required this status synchronization; this entry closes that
minor documentation finding without changing the frozen r4 implementation candidate.

### M3 revision 1 review block (2026-09-05)

CommitSet `75cfd2b1-fba3-4c19-8ebf-f0e63cd07afe` freezes Writing Ops
`4bb1f51360e139a87428e5cb41da019666b6f8fe` and installed build
`0.1.0+codex.20260905060404` / `sha256:5f7e288474e098be2e929a4c015d4dc9711295907558fc4aa275e5abd5ef9f0c`.
Its independent review `f67d1655-ca03-4617-95ec-ab587cfff85e` failed; all outputs remain
`human_review_status=pending`.

`M3-R1-IMP-001` is a bounded ReviewPacket integrity repair: `previous_findings` and
`revision_relationships` were included in packet text but omitted from its hash map. The M3
archive, skill lock, development-link exclusion, and M4/M5 exclusions passed review. Repair the
two omitted hashes, rerun the M3 gates, freeze a new CommitSet, and obtain a fresh review.

### M3 revision 2 review block (2026-09-05)

CommitSet `8b980977-b09b-42a4-9284-45ecfe2b5a37` freezes Writing Ops
`632c68f38157cc939f089cb71f5e0f652b1d0458` and installed build
`0.1.0+codex.20260905061526` / `sha256:75079bb45ae40383edffe250a845fe484b4dec747e85e0800d4300c6014b461b`.
Its independent review `634c9364-6c03-4d0f-a5cb-3baa0b8d3b2b` failed; all outputs remain
`human_review_status=pending`.

`M3-R2-IMP-001` requires detached packet values: caller mutation after construction must not alter
the packet or invalidate its precomputed hashes. `M3-R2-IMP-002` records the intended seam: M3
constructs and freezes the packet, while M5 is the only milestone allowed to submit it as Codex
input. Repair the immutable snapshot and rerun the bounded M3 review.

### M3 revision 3 closure (2026-09-05)

CommitSet `835ef709-a878-4a05-a17f-ccc5cc14c5f6` freezes Writing Ops
`a554b87aae74e4c649b871f14ba52ed0ea3a4f2b` and installed build
`0.1.0+codex.20260905062305` / `sha256:f8b6f3699b7fc92fe32f26c4a80b49a67dae7a9f42a187481e4666cefc93bdde`.
Its independent review `98eb1d7a-903e-4f8f-822c-67c7d90aac10` passed with the non-blocking
`M3-R3-TEST-001` coverage finding. All outputs remain `human_review_status=pending`.

M3 is complete: the installed package contains only the locked PlotRail skill closure, and its
ReviewPacket detaches and hashes every mutable review input. M5 remains responsible for actual
Codex-input dispatch. The recorded finding asks for broader mutation assertions but does not block
M4 routing.
