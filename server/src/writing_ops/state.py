from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

GoalLevel = Literal["long_term", "cycle", "daily"]

TABLES = (
    "long_term_goal",
    "cycle_plan",
    "daily_goal",
    "goal_approval",
    "run",
    "step",
    "gate_receipt",
    "trace_event",
    "artifact",
    "commit_set",
    "milestone_review",
    "human_review",
    "adoption_record",
    "execution_lease",
)

DAILY_REQUIRED = {
    "project",
    "book",
    "chapter",
    "content_purpose",
    "must_happen",
    "must_not_happen",
    "pov",
    "tone",
    "word_count",
    "forbidden_zones",
    "window_start",
    "window_end",
    "auto_adopt",
}

RUN_TRANSITIONS = {
    "pending": {"claimed", "cancelled", "blocked"},
    "claimed": {"running", "cancelled", "blocked"},
    "running": {"awaiting_review", "reconciling", "failed", "cancelled", "blocked"},
    "awaiting_review": {"running", "reconciling", "completed", "blocked"},
    "reconciling": {"running", "completed", "manual_reconcile", "blocked"},
    "manual_reconcile": set(),
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    "blocked": set(),
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def default_data_root() -> Path:
    configured = os.environ.get("WRITING_OPS_DATA_ROOT")
    if configured:
        return Path(configured)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is required for Writing Ops state")
    return Path(local_app_data) / "WritingOps"


def validate_transition(current: str, target: str) -> None:
    if target not in RUN_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid run transition: {current} -> {target}")


class StateStore:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or (default_data_root() / "writing-ops.sqlite3")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS schema_migration (
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS long_term_goal (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                    human_review_status TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY (id, revision)
                );
                CREATE TABLE IF NOT EXISTS cycle_plan (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, long_term_id TEXT NOT NULL,
                    long_term_revision INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                    human_review_status TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY (id, revision)
                );
                CREATE TABLE IF NOT EXISTS daily_goal (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, long_term_id TEXT NOT NULL,
                    long_term_revision INTEGER NOT NULL, cycle_id TEXT NOT NULL,
                    cycle_revision INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                    human_review_status TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY (id, revision)
                );
                CREATE TABLE IF NOT EXISTS goal_approval (
                    id TEXT PRIMARY KEY, daily_goal_id TEXT NOT NULL, daily_revision INTEGER NOT NULL,
                    long_term_revision INTEGER NOT NULL, cycle_revision INTEGER NOT NULL,
                    payload_hash TEXT NOT NULL, timezone TEXT NOT NULL, expires_at TEXT NOT NULL,
                    auto_adopt INTEGER NOT NULL, consumed_at TEXT, invalidated_reason TEXT,
                    created_at TEXT NOT NULL, human_review_status TEXT NOT NULL DEFAULT 'pending'
                );
                CREATE TABLE IF NOT EXISTS run (
                    id TEXT PRIMARY KEY, daily_goal_id TEXT NOT NULL, daily_revision INTEGER NOT NULL,
                    approval_id TEXT, state TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, human_review_status TEXT NOT NULL DEFAULT 'pending'
                );
                CREATE TABLE IF NOT EXISTS step (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
                    idempotency_key TEXT, intent_json TEXT, ack_json TEXT, outcome TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    human_review_status TEXT NOT NULL DEFAULT 'pending'
                );
                CREATE TABLE IF NOT EXISTS gate_receipt (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at TEXT NOT NULL, human_review_status TEXT NOT NULL DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS trace_event (run_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, previous_hash TEXT, event_hash TEXT NOT NULL, created_at TEXT NOT NULL, human_review_status TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY (run_id, sequence));
                CREATE TABLE IF NOT EXISTS artifact (id TEXT PRIMARY KEY, run_id TEXT, kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL, human_review_status TEXT NOT NULL DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS commit_set (id TEXT PRIMARY KEY, milestone_id TEXT NOT NULL, revision INTEGER NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at TEXT NOT NULL, human_review_status TEXT NOT NULL DEFAULT 'pending', UNIQUE (milestone_id, revision));
                CREATE TABLE IF NOT EXISTS milestone_review (id TEXT PRIMARY KEY, milestone_id TEXT NOT NULL, commit_set_id TEXT NOT NULL, verdict TEXT NOT NULL, findings_json TEXT NOT NULL, created_at TEXT NOT NULL, human_review_status TEXT NOT NULL DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS human_review (id TEXT PRIMARY KEY, subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, status TEXT NOT NULL, comment TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS adoption_record (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, storyforge_record_id TEXT, state TEXT NOT NULL, created_at TEXT NOT NULL, human_review_status TEXT NOT NULL DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS execution_lease (task_id TEXT PRIMARY KEY, milestone_id TEXT NOT NULL, owner_run_id TEXT NOT NULL, heartbeat_at TEXT NOT NULL, expires_at TEXT NOT NULL, worker_fingerprint TEXT NOT NULL);
                INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES (1, CURRENT_TIMESTAMP);
                COMMIT;
                """
            )

    def table_names(self) -> set[str]:
        with self.connect() as db:
            rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {str(row["name"]) for row in rows}

    def _next_revision(self, db: sqlite3.Connection, table: str, goal_id: str) -> int:
        row = db.execute(
            f"SELECT COALESCE(MAX(revision), 0) + 1 AS revision FROM {table} WHERE id = ?",
            (goal_id,),
        ).fetchone()
        return int(row["revision"])

    def upsert_goal(
        self,
        level: GoalLevel,
        payload: dict[str, Any],
        *,
        goal_id: str | None = None,
        long_term_id: str | None = None,
        long_term_revision: int | None = None,
        cycle_id: str | None = None,
        cycle_revision: int | None = None,
    ) -> dict[str, Any]:
        table = {"long_term": "long_term_goal", "cycle": "cycle_plan", "daily": "daily_goal"}[level]
        goal_id = goal_id or str(uuid.uuid4())
        now = utc_now().isoformat()
        encoded = canonical_json(payload)
        digest = payload_hash(payload)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = self._next_revision(db, table, goal_id)
            if level == "long_term":
                db.execute(
                    "INSERT INTO long_term_goal VALUES (?, ?, ?, ?, ?, 'pending')",
                    (goal_id, revision, encoded, digest, now),
                )
            elif level == "cycle":
                if not long_term_id or long_term_revision is None:
                    raise ValueError("cycle plan requires a long-term goal revision")
                db.execute(
                    "INSERT INTO cycle_plan VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
                    (goal_id, revision, long_term_id, long_term_revision, encoded, digest, now),
                )
            else:
                if not long_term_id or long_term_revision is None or not cycle_id or cycle_revision is None:
                    raise ValueError("daily goal requires long-term and cycle revisions")
                missing = sorted(DAILY_REQUIRED - payload.keys())
                if missing:
                    raise ValueError(f"daily goal missing required fields: {', '.join(missing)}")
                db.execute(
                    "INSERT INTO daily_goal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
                    (goal_id, revision, long_term_id, long_term_revision, cycle_id, cycle_revision, encoded, digest, now),
                )
            db.commit()
        return {"id": goal_id, "revision": revision, "payload_hash": digest, "human_review_status": "pending"}

    def get_goal(self, level: GoalLevel, goal_id: str, revision: int | None = None) -> dict[str, Any] | None:
        table = {"long_term": "long_term_goal", "cycle": "cycle_plan", "daily": "daily_goal"}[level]
        with self.connect() as db:
            if revision is None:
                row = db.execute(
                    f"SELECT * FROM {table} WHERE id = ? ORDER BY revision DESC LIMIT 1",
                    (goal_id,),
                ).fetchone()
            else:
                row = db.execute(
                    f"SELECT * FROM {table} WHERE id = ? AND revision = ?",
                    (goal_id, revision),
                ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def approve_daily_goal(
        self,
        daily_goal_id: str,
        daily_revision: int,
        timezone: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        now = utc_now()
        if expires_at <= now:
            raise ValueError("approval expiry must be in the future")
        daily = self.get_goal("daily", daily_goal_id, daily_revision)
        if daily is None:
            raise ValueError("daily goal revision not found")
        approval_id = str(uuid.uuid4())
        with self.connect() as db:
            latest_long = db.execute(
                "SELECT MAX(revision) AS revision FROM long_term_goal WHERE id = ?",
                (daily["long_term_id"],),
            ).fetchone()["revision"]
            latest_cycle = db.execute(
                "SELECT MAX(revision) AS revision FROM cycle_plan WHERE id = ?",
                (daily["cycle_id"],),
            ).fetchone()["revision"]
            if latest_long != daily["long_term_revision"] or latest_cycle != daily["cycle_revision"]:
                raise ValueError("daily goal parent revision is stale")
            db.execute(
                """INSERT INTO goal_approval (
                    id, daily_goal_id, daily_revision, long_term_revision, cycle_revision,
                    payload_hash, timezone, expires_at, auto_adopt, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval_id,
                    daily_goal_id,
                    daily_revision,
                    daily["long_term_revision"],
                    daily["cycle_revision"],
                    daily["payload_hash"],
                    timezone,
                    expires_at.isoformat(),
                    int(bool(daily["payload"]["auto_adopt"])),
                    now.isoformat(),
                ),
            )
        return {
            "approval_id": approval_id,
            "daily_goal_id": daily_goal_id,
            "daily_revision": daily_revision,
            "payload_hash": daily["payload_hash"],
            "expires_at": expires_at.isoformat(),
            "human_review_status": "pending",
        }

    def validate_approval(self, approval_id: str, now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        with self.connect() as db:
            approval = db.execute(
                "SELECT * FROM goal_approval WHERE id = ?", (approval_id,)
            ).fetchone()
            if approval is None:
                return {"valid": False, "reason": "not_found"}
            daily = db.execute(
                "SELECT * FROM daily_goal WHERE id = ? AND revision = ?",
                (approval["daily_goal_id"], approval["daily_revision"]),
            ).fetchone()
            latest_daily = db.execute(
                "SELECT MAX(revision) AS revision FROM daily_goal WHERE id = ?",
                (approval["daily_goal_id"],),
            ).fetchone()["revision"]
            latest_long = db.execute(
                "SELECT MAX(revision) AS revision FROM long_term_goal WHERE id = ?",
                (daily["long_term_id"],),
            ).fetchone()["revision"]
            latest_cycle = db.execute(
                "SELECT MAX(revision) AS revision FROM cycle_plan WHERE id = ?",
                (daily["cycle_id"],),
            ).fetchone()["revision"]
        reason = None
        if approval["consumed_at"]:
            reason = "consumed"
        elif datetime.fromisoformat(approval["expires_at"]) <= now:
            reason = "expired"
        elif latest_daily != approval["daily_revision"]:
            reason = "daily_revision_changed"
        elif latest_long != approval["long_term_revision"]:
            reason = "long_term_revision_changed"
        elif latest_cycle != approval["cycle_revision"]:
            reason = "cycle_revision_changed"
        elif daily["payload_hash"] != approval["payload_hash"]:
            reason = "payload_changed"
        return {"valid": reason is None, "reason": reason, "approval_id": approval_id}

    def acquire_lease(
        self,
        task_id: str,
        milestone_id: str,
        owner_run_id: str,
        worker_fingerprint: str,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM execution_lease WHERE task_id = ?", (task_id,)).fetchone()
            if (
                current
                and datetime.fromisoformat(current["expires_at"]) > now
                and current["owner_run_id"] != owner_run_id
            ):
                db.rollback()
                return False
            db.execute(
                "INSERT OR REPLACE INTO execution_lease VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, milestone_id, owner_run_id, now.isoformat(), expires_at.isoformat(), worker_fingerprint),
            )
            db.commit()
        return True

    def release_lease(self, task_id: str, owner_run_id: str) -> bool:
        with self.connect() as db:
            result = db.execute(
                "DELETE FROM execution_lease WHERE task_id = ? AND owner_run_id = ?",
                (task_id, owner_run_id),
            )
        return result.rowcount == 1

    def heartbeat_lease(
        self, task_id: str, owner_run_id: str, heartbeat_at: datetime, expires_at: datetime
    ) -> bool:
        with self.connect() as db:
            result = db.execute(
                """UPDATE execution_lease SET heartbeat_at = ?, expires_at = ?
                   WHERE task_id = ? AND owner_run_id = ? AND expires_at > ?""",
                (
                    heartbeat_at.isoformat(),
                    expires_at.isoformat(),
                    task_id,
                    owner_run_id,
                    heartbeat_at.isoformat(),
                ),
            )
        return result.rowcount == 1

    def get_lease(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM execution_lease WHERE task_id = ?", (task_id,)
            ).fetchone()
        return dict(row) if row else None
