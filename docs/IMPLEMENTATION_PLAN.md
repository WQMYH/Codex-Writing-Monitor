# Writing Ops unattended writing console implementation plan

Plan revision: `2026-09-01-r1`

This is the approved execution-order source for the Writing Ops plugin. It contains
requirements, boundaries, milestones, gates, and commit/review policy. It never records
current progress. Current state lives only in `docs/IMPLEMENTATION_STATUS.md`.

## Goal and authority

- Build the independent Git repository plugin at `plugins/writing-ops` and distribute it
  through the existing `gameops-local` marketplace as `写作运行台`.
- Storyforge is the only authority for manuscript text, canon, and project state.
- Writing MCP is a read-only knowledge layer.
- PlotRail works only on hash-bound snapshots in an isolated Run directory.
- v1 never publishes externally and does not promise unattended operation while Windows is
  locked, asleep, logged out, or Codex is closed.
- Every durable output starts with `human_review_status=pending`; independent review does not
  constitute user acceptance.

## Execution and recovery protocol

1. Before work, read the unique status source, the latest applicable ReviewResult, Git state,
   and ExecutionLease.
2. A valid lease owned by an active task or worker prevents dispatch, restart, takeover, or
   duplicate work.
3. Resume only from durable acknowledgements. Unknown side-effect outcomes route to read-only
   reconciliation and never blindly replay generation, revision, pairing, or adoption.
4. Each side-effecting step persists intent before dispatch, then records durable acknowledgement
   or `unknown_outcome`, followed by reconciliation.
5. New authorization, third-party login, changed security scope, or `manual_reconcile` is a real
   block. A heartbeat remains quiet while the block is unchanged.
6. The engineering heartbeat is a recovery trigger, not a parallel worker. It pauses after M6,
   cancellation, or explicit pause.

## CommitSet and review policy

- Commit independently rollback-able fixes and stable phase outcomes; do not push automatically.
- At a milestone boundary, all related tracked changes are committed, the relevant machine gates
  pass, and an immutable CommitSet freezes repository SHAs and acceptance receipts.
- A fresh no-history reviewer checks the exact frozen candidate. Findings, repairs, machine gates,
  commits, installed-cache smoke, CommitSet revisions, and review results are distinct transitions.
- Critical or Important findings keep the milestone incomplete. Repair follows failing evidence
  first, bounded implementation, complete gates, a new CommitSet, and the review policy selected by
  the active execution protocol.
- Review-budget exhaustion trips a breaker. It is not reset by renaming, refreezing, raising risk,
  or rewriting the plan. Recovery requires an explicit remediation protocol rather than silently
  opening another ordinary review round.
- A user rejection invalidates dependent later milestones and returns execution to the earliest
  rejected CommitSet for repair and renewed evidence.

## State, MCP, and dashboard contracts

- Persist operational data under `%LOCALAPPDATA%\WritingOps`, outside plugin cache.
- Goal edits create immutable revisions. Daily approval binds the complete three-level goal
  payload, hashes, local timezone, expiry, and auto-adoption authority.
- Parent revision changes, date expiry, clock anomaly, or payload changes invalidate approval.
- Expose the approved read tools and interactive write tools; `writing_run_due` is the only
  unattended write entry. It uses `claim -> poll -> submit_review -> reconcile` and never causes
  the MCP server to call Codex in reverse.
- One ViewModel feeds the Codex MCP Apps renderer, structured Markdown/text fallback, and the
  Storyforge `/writing-ops` fallback page.
- The dashboard shows goals, runs, steps, findings, artifacts, CommitSets, review status, runtime
  health, blockers, and next actions without becoming a second state authority.

## Writing, trace, and adoption boundaries

- ReviewPacket includes effective goals, chapter contract, full candidate, Writing MCP evidence,
  prior findings, revision relationships, and version hashes as actual Codex input.
- Candidate text is untrusted data and cannot expand tool, publication, URL, origin, selector, or
  shell authority.
- Deterministic checks and required semantic dimensions must pass; `uncertain` blocks adoption.
  Authorized P1/P2 repairs are bounded to two writing revisions, with every full version and
  finding-to-revision evidence preserved.
- Storyforge adoption uses one transactional compare-and-swap command and a unique AdoptionRecord.
  Unknown results are reconciled as confirmed adopted, confirmed not adopted, or manual reconcile;
  adoption is never blindly replayed.
- M2 does not persist Artifact or Trace content. M5 introduces their redaction, atomic replacement,
  and hash-chain sequencing after its recovery boundary is implemented.

## Runtime and browser boundary

- Runtime supervision verifies process identity, executable path, configuration fingerprint,
  nonce, PID creation time, ports, profile lock, and exact approved Origins.
- Dedicated Edge uses a separate user-data directory and profile lock. Unknown port owners are
  reported, never terminated.
- browser-use is pinned to `0.13.8` in an isolated Python 3.12 worker and is a bounded fallback, not
  a second autonomous LLM agent.
- M4 owns loopback listener lifecycle and the one-shot capability handoff to Storyforge; M2 may only
  provide its sealed component and factory.
- Codex in-app Browser is limited to attended diagnostics. An Edge extension is not a v1 dependency
  and is never silently installed, authorized, or logged in.

## Milestones and completion gates

### M0 — Host and recovery probe

Create the plugin repository and prove the two-minute recovery trigger, active-task non-interference,
plugin cache/install path, MCP Apps capability probe, text fallback, fixed dashboard task, and
scheduled-task plugin visibility.

### M1 — Core contracts

Implement manifest and MCP schemas, SQLite migrations, immutable goal/approval contracts, run state
machine, ExecutionLease, implementation ledger, and fake runtime adapters. No external runtime starts.

### M2 — Dashboard and review projection

Implement three-level goals, creator/reviewer views, CommitSet, review state, and the three renderers
over one ViewModel. Artifact and Trace may be projected when already present, but M2 creates neither.

### M3 — Skills and context

Implement PlotRail links, clean-source `git archive` materialization, skill lock, facade, and complete
ReviewPacket construction.

### M4 — Runtime and browser

Implement Windows supervision, pairing-code interception, Edge profile locking, exact Origins,
browser-use worker, and stable Storyforge identity.

### M5 — Review and adoption

Implement multi-turn Codex verdicts, bounded revision, GateReceipt, Storyforge CAS adoption, and
unknown-outcome reconciliation.

### M6 — Real unattended acceptance

Run from installed cache and a real scheduled trigger; verify unattended completion, interruption
recovery, installation/fixed task behavior, two consecutive scheduled dates, and operating docs.

## Milestone definition of done

Every milestone requires machine gates, committed tracked changes, a frozen CommitSet, the applicable
independent review, pending human review markings, an updated unique status source, and no open safety
or reconciliation gap. Later milestones do not start while an earlier gate remains open.

## Document roles

- Contract and safety: `docs/SECURITY.md`, `.mcp.json`, `.codex-plugin/plugin.json`.
- Unique status source: `docs/IMPLEMENTATION_STATUS.md`.
- Review evidence: `.skillflow/reviews/`.
- Test surfaces: `server/tests/`, `ui/src/*.test.tsx`, plugin validation and installed-cache smoke.
- Execution protocol: `.agents/skills/writing-ops-plan/SKILL.md`.
