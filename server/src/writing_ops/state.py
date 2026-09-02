from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from writing_ops.models import CommitSetPayload

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


class DailyContract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    project: str = Field(min_length=1)
    book: str = Field(min_length=1)
    chapter: str = Field(min_length=1)
    content_purpose: str = Field(min_length=1)
    must_happen: list[str]
    must_not_happen: list[str]
    pov: str = Field(min_length=1)
    tone: str = Field(min_length=1)
    word_count: int = Field(gt=0)
    forbidden_zones: list[str]
    window_start: str
    window_end: str
    auto_adopt: bool

    @model_validator(mode="after")
    def valid_window(self) -> DailyContract:
        start = datetime.fromisoformat(self.window_start)
        end = datetime.fromisoformat(self.window_end)
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("daily window must be aware and increasing")
        return self


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

ARTIFACT_SUFFIXES = {
    "candidate_text": ".txt",
    "review_text": ".txt",
    "security_screenshot": ".png",
    "commit_set": ".json",
    "trace_export": ".json",
}

TRACE_PAYLOAD_FIELDS = {
    "step_intent": {"step_id", "kind", "state"},
    "step_ack": {"step_id", "outcome", "state"},
    "artifact_registered": {"artifact_id", "kind", "sha256"},
    "runtime_status": {"component", "state", "pid", "port", "detail"},
    "browser_action": {"action", "origin", "result", "error_code"},
    "finding": {"finding_id", "severity", "dimension", "status"},
    "heartbeat_skipped_active": {"task_id", "milestone_id"},
}

SECRET_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:authorization|proxy-authorization)\s*[:=]\s*(?:bearer|basic)?\s*[A-Za-z0-9._~+/=-]{8,}",
        r"\b(?:cookie|set-cookie)\s*[:=]\s*[^\r\n]{4,}",
        r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|session(?:[_-]?token)?|csrf(?:[_-]?token)?|pairing[_-]?code|password|client[_-]?secret)\b\s*[:=]\s*[\"']?[^\s\"',;}]{4,}",
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
    )
)


class TracePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class StepIntentPayload(TracePayload):
    step_id: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=128)


class StepAckPayload(TracePayload):
    step_id: str = Field(min_length=1, max_length=256)
    outcome: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=1, max_length=128)


class ArtifactRegisteredPayload(TracePayload):
    artifact_id: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RuntimeStatusPayload(TracePayload):
    component: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=128)
    pid: int | None
    port: int | None = Field(default=None, ge=1, le=65535)
    detail: str = Field(max_length=2048)


class BrowserActionPayload(TracePayload):
    action: str = Field(min_length=1, max_length=128)
    origin: str = Field(min_length=1, max_length=2048)
    result: str = Field(max_length=2048)
    error_code: str | None = Field(default=None, max_length=128)


class FindingPayload(TracePayload):
    finding_id: str = Field(min_length=1, max_length=256)
    severity: str = Field(min_length=1, max_length=64)
    dimension: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=128)


class HeartbeatSkippedPayload(TracePayload):
    task_id: str = Field(min_length=1, max_length=256)
    milestone_id: str = Field(min_length=1, max_length=64)


TRACE_PAYLOAD_MODELS: dict[str, type[TracePayload]] = {
    "step_intent": StepIntentPayload,
    "step_ack": StepAckPayload,
    "artifact_registered": ArtifactRegisteredPayload,
    "runtime_status": RuntimeStatusPayload,
    "browser_action": BrowserActionPayload,
    "finding": FindingPayload,
    "heartbeat_skipped_active": HeartbeatSkippedPayload,
}

HUMAN_REVIEW_SUBJECTS = {
    "artifact": "artifact",
    "commit_set": "commit_set",
    "milestone_review": "milestone_review",
    "run": "run",
    "gate_receipt": "gate_receipt",
    "adoption_record": "adoption_record",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalized_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def parse_approval_expiry(timezone: Any, expires_at: Any) -> datetime:
    if not isinstance(timezone, str) or not isinstance(expires_at, str):
        raise ValueError("approval time fields must be text")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("unrecognized approval timezone") from error
    try:
        parsed = datetime.fromisoformat(expires_at)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid approval expiry") from error
    return normalized_utc(parsed)


def approval_time_valid(timezone: Any, expires_at: Any) -> int:
    try:
        parse_approval_expiry(timezone, expires_at)
    except ValueError:
        return 0
    return 1


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_strings(item)


def reject_secret_material(value: Any) -> None:
    for text in _walk_strings(value):
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise ValueError("secret material must not be persisted")


def safe_artifact_content(kind: str, content: bytes) -> bytes:
    if kind == "security_screenshot":
        raise ValueError("security screenshot persistence requires the M4 redaction pipeline")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("text artifact content must be valid UTF-8") from error
    reject_secret_material(text)
    return content


def fsync_parent_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def normalized_trace_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = TRACE_PAYLOAD_MODELS.get(event_type)
    if model is None:
        raise ValueError("trace event type and fields must be allowlisted")
    try:
        normalized = model.model_validate(payload).model_dump(mode="json")
    except ValueError as error:
        raise ValueError(f"trace payload is invalid: {error}") from error
    reject_secret_material(normalized)
    return normalized


def canonical_json_hash(raw_json: str) -> str:
    try:
        return payload_hash(json.loads(raw_json))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""


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
        connection.create_function(
            "canonical_json_hash", 1, canonical_json_hash, deterministic=True
        )
        connection.create_function(
            "approval_time_valid", 2, approval_time_valid, deterministic=True
        )
        connection.execute("PRAGMA recursive_triggers = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        backup_path = self.database_path.with_name(
            f".{self.database_path.name}.{uuid.uuid4().hex}.migration-backup"
        )
        database_existed = self.database_path.exists()
        if database_existed:
            with (
                closing(sqlite3.connect(self.database_path)) as source,
                closing(sqlite3.connect(backup_path)) as backup,
            ):
                source.backup(backup)
        try:
            self._migrate_in_place()
        except Exception:
            if database_existed:
                with (
                    closing(sqlite3.connect(backup_path)) as backup,
                    closing(sqlite3.connect(self.database_path)) as destination,
                ):
                    backup.backup(destination)
            else:
                self.database_path.unlink(missing_ok=True)
            raise
        finally:
            backup_path.unlink(missing_ok=True)

    def _migrate_in_place(self) -> None:
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
                    human_review_status TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY (id, revision),
                    FOREIGN KEY (long_term_id, long_term_revision)
                      REFERENCES long_term_goal(id, revision)
                );
                CREATE TABLE IF NOT EXISTS daily_goal (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, long_term_id TEXT NOT NULL,
                    long_term_revision INTEGER NOT NULL, cycle_id TEXT NOT NULL,
                    cycle_revision INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                    human_review_status TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY (id, revision),
                    FOREIGN KEY (long_term_id, long_term_revision)
                      REFERENCES long_term_goal(id, revision),
                    FOREIGN KEY (cycle_id, cycle_revision)
                      REFERENCES cycle_plan(id, revision)
                );
                CREATE TABLE IF NOT EXISTS goal_approval (
                    id TEXT PRIMARY KEY, daily_goal_id TEXT NOT NULL, daily_revision INTEGER NOT NULL,
                    long_term_id TEXT NOT NULL, long_term_revision INTEGER NOT NULL,
                    cycle_id TEXT NOT NULL, cycle_revision INTEGER NOT NULL,
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
                CREATE TRIGGER IF NOT EXISTS cycle_parent_guard BEFORE INSERT ON cycle_plan
                WHEN NOT EXISTS (SELECT 1 FROM long_term_goal WHERE id = NEW.long_term_id AND revision = NEW.long_term_revision)
                BEGIN SELECT RAISE(ABORT, 'missing long-term parent'); END;
                CREATE TRIGGER IF NOT EXISTS daily_parent_guard BEFORE INSERT ON daily_goal
                WHEN NOT EXISTS (
                  SELECT 1 FROM cycle_plan c JOIN long_term_goal l
                    ON l.id = c.long_term_id AND l.revision = c.long_term_revision
                  WHERE c.id = NEW.cycle_id AND c.revision = NEW.cycle_revision
                    AND c.long_term_id = NEW.long_term_id
                    AND c.long_term_revision = NEW.long_term_revision
                )
                BEGIN SELECT RAISE(ABORT, 'inconsistent daily parent chain'); END;
                DROP TRIGGER IF EXISTS cycle_parent_update_guard;
                DROP TRIGGER IF EXISTS daily_parent_update_guard;
                CREATE TRIGGER cycle_parent_update_guard BEFORE UPDATE OF long_term_id, long_term_revision ON cycle_plan
                WHEN NOT EXISTS (SELECT 1 FROM long_term_goal WHERE id = NEW.long_term_id AND revision = NEW.long_term_revision)
                  OR EXISTS (
                    SELECT 1 FROM daily_goal d
                    WHERE d.cycle_id = OLD.id AND d.cycle_revision = OLD.revision
                      AND (d.long_term_id != NEW.long_term_id OR d.long_term_revision != NEW.long_term_revision)
                  )
                BEGIN SELECT RAISE(ABORT, 'missing long-term parent'); END;
                CREATE TRIGGER daily_parent_update_guard BEFORE UPDATE OF long_term_id, long_term_revision, cycle_id, cycle_revision ON daily_goal
                WHEN NOT EXISTS (
                  SELECT 1 FROM cycle_plan c WHERE c.id = NEW.cycle_id AND c.revision = NEW.cycle_revision
                    AND c.long_term_id = NEW.long_term_id AND c.long_term_revision = NEW.long_term_revision
                )
                BEGIN SELECT RAISE(ABORT, 'inconsistent daily parent chain'); END;
                DROP TRIGGER IF EXISTS daily_contract_guard;
                DROP TRIGGER IF EXISTS daily_contract_update_guard;
                CREATE TRIGGER daily_contract_guard BEFORE INSERT ON daily_goal
                WHEN json_valid(NEW.payload_json) = 0
                  OR (SELECT COUNT(*) FROM json_each(NEW.payload_json)) != 13
                  OR EXISTS (
                    SELECT 1 FROM json_each(NEW.payload_json)
                    WHERE key NOT IN (
                      'project','book','chapter','content_purpose','must_happen',
                      'must_not_happen','pov','tone','word_count','forbidden_zones',
                      'window_start','window_end','auto_adopt'
                    )
                  )
                  OR json_type(NEW.payload_json, '$.project') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.project')) = ''
                  OR json_type(NEW.payload_json, '$.book') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.book')) = ''
                  OR json_type(NEW.payload_json, '$.chapter') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.chapter')) = ''
                  OR json_type(NEW.payload_json, '$.content_purpose') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.content_purpose')) = ''
                  OR json_type(NEW.payload_json, '$.pov') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.pov')) = ''
                  OR json_type(NEW.payload_json, '$.tone') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.tone')) = ''
                  OR json_type(NEW.payload_json, '$.auto_adopt') NOT IN ('true','false')
                  OR json_type(NEW.payload_json, '$.word_count') != 'integer'
                  OR json_extract(NEW.payload_json, '$.word_count') <= 0
                  OR json_type(NEW.payload_json, '$.must_happen') != 'array'
                  OR EXISTS (SELECT 1 FROM json_each(NEW.payload_json, '$.must_happen') WHERE type != 'text')
                  OR json_type(NEW.payload_json, '$.must_not_happen') != 'array'
                  OR EXISTS (SELECT 1 FROM json_each(NEW.payload_json, '$.must_not_happen') WHERE type != 'text')
                  OR json_type(NEW.payload_json, '$.forbidden_zones') != 'array'
                  OR EXISTS (SELECT 1 FROM json_each(NEW.payload_json, '$.forbidden_zones') WHERE type != 'text')
                  OR json_type(NEW.payload_json, '$.window_start') != 'text'
                  OR json_type(NEW.payload_json, '$.window_end') != 'text'
                  OR julianday(json_extract(NEW.payload_json, '$.window_start')) IS NULL
                  OR julianday(json_extract(NEW.payload_json, '$.window_end')) IS NULL
                  OR julianday(json_extract(NEW.payload_json, '$.window_end')) <= julianday(json_extract(NEW.payload_json, '$.window_start'))
                  OR NOT (
                    json_extract(NEW.payload_json, '$.window_start') GLOB '*[+-][0-9][0-9]:[0-9][0-9]'
                    OR substr(json_extract(NEW.payload_json, '$.window_start'), -1) = 'Z'
                  )
                  OR NOT (
                    json_extract(NEW.payload_json, '$.window_end') GLOB '*[+-][0-9][0-9]:[0-9][0-9]'
                    OR substr(json_extract(NEW.payload_json, '$.window_end'), -1) = 'Z'
                  )
                  OR canonical_json_hash(NEW.payload_json) != NEW.payload_hash
                BEGIN SELECT RAISE(ABORT, 'invalid daily contract'); END;
                CREATE TRIGGER daily_contract_update_guard BEFORE UPDATE OF payload_json, payload_hash ON daily_goal
                WHEN json_valid(NEW.payload_json) = 0
                  OR (SELECT COUNT(*) FROM json_each(NEW.payload_json)) != 13
                  OR EXISTS (
                    SELECT 1 FROM json_each(NEW.payload_json)
                    WHERE key NOT IN (
                      'project','book','chapter','content_purpose','must_happen',
                      'must_not_happen','pov','tone','word_count','forbidden_zones',
                      'window_start','window_end','auto_adopt'
                    )
                  )
                  OR json_type(NEW.payload_json, '$.project') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.project')) = ''
                  OR json_type(NEW.payload_json, '$.book') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.book')) = ''
                  OR json_type(NEW.payload_json, '$.chapter') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.chapter')) = ''
                  OR json_type(NEW.payload_json, '$.content_purpose') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.content_purpose')) = ''
                  OR json_type(NEW.payload_json, '$.pov') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.pov')) = ''
                  OR json_type(NEW.payload_json, '$.tone') != 'text'
                  OR trim(json_extract(NEW.payload_json, '$.tone')) = ''
                  OR json_type(NEW.payload_json, '$.auto_adopt') NOT IN ('true','false')
                  OR json_type(NEW.payload_json, '$.word_count') != 'integer'
                  OR json_extract(NEW.payload_json, '$.word_count') <= 0
                  OR json_type(NEW.payload_json, '$.must_happen') != 'array'
                  OR EXISTS (SELECT 1 FROM json_each(NEW.payload_json, '$.must_happen') WHERE type != 'text')
                  OR json_type(NEW.payload_json, '$.must_not_happen') != 'array'
                  OR EXISTS (SELECT 1 FROM json_each(NEW.payload_json, '$.must_not_happen') WHERE type != 'text')
                  OR json_type(NEW.payload_json, '$.forbidden_zones') != 'array'
                  OR EXISTS (SELECT 1 FROM json_each(NEW.payload_json, '$.forbidden_zones') WHERE type != 'text')
                  OR json_type(NEW.payload_json, '$.window_start') != 'text'
                  OR json_type(NEW.payload_json, '$.window_end') != 'text'
                  OR julianday(json_extract(NEW.payload_json, '$.window_start')) IS NULL
                  OR julianday(json_extract(NEW.payload_json, '$.window_end')) IS NULL
                  OR julianday(json_extract(NEW.payload_json, '$.window_end')) <= julianday(json_extract(NEW.payload_json, '$.window_start'))
                  OR NOT (
                    json_extract(NEW.payload_json, '$.window_start') GLOB '*[+-][0-9][0-9]:[0-9][0-9]'
                    OR substr(json_extract(NEW.payload_json, '$.window_start'), -1) = 'Z'
                  )
                  OR NOT (
                    json_extract(NEW.payload_json, '$.window_end') GLOB '*[+-][0-9][0-9]:[0-9][0-9]'
                    OR substr(json_extract(NEW.payload_json, '$.window_end'), -1) = 'Z'
                  )
                  OR canonical_json_hash(NEW.payload_json) != NEW.payload_hash
                BEGIN SELECT RAISE(ABORT, 'invalid daily contract'); END;
                INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES (3, CURRENT_TIMESTAMP);
                COMMIT;
                """
            )
            approval_columns = {
                str(row["name"]) for row in db.execute("PRAGMA table_info(goal_approval)")
            }
            missing_identity_columns = {
                "long_term_id",
                "cycle_id",
            } - approval_columns
            if missing_identity_columns:
                db.execute("BEGIN IMMEDIATE")
                if "long_term_id" in missing_identity_columns:
                    db.execute("ALTER TABLE goal_approval ADD COLUMN long_term_id TEXT")
                if "cycle_id" in missing_identity_columns:
                    db.execute("ALTER TABLE goal_approval ADD COLUMN cycle_id TEXT")
                db.execute(
                    """UPDATE goal_approval SET
                       long_term_id = (
                         SELECT d.long_term_id FROM daily_goal d
                         WHERE d.id = goal_approval.daily_goal_id
                           AND d.revision = goal_approval.daily_revision
                       ),
                       cycle_id = (
                         SELECT d.cycle_id FROM daily_goal d
                         WHERE d.id = goal_approval.daily_goal_id
                           AND d.revision = goal_approval.daily_revision
                       )
                       WHERE long_term_id IS NULL OR cycle_id IS NULL"""
                )
                unresolved = db.execute(
                    """SELECT 1 FROM goal_approval
                       WHERE long_term_id IS NULL OR cycle_id IS NULL LIMIT 1"""
                ).fetchone()
                if unresolved:
                    db.rollback()
                    raise RuntimeError("migrated approval parent identity is unresolved")
                db.commit()
            db.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TRIGGER IF NOT EXISTS long_term_payload_guard
                BEFORE INSERT ON long_term_goal
                WHEN json_valid(NEW.payload_json) = 0
                  OR json_type(NEW.payload_json) != 'object'
                  OR canonical_json_hash(NEW.payload_json) != NEW.payload_hash
                BEGIN SELECT RAISE(ABORT, 'invalid long-term payload'); END;
                CREATE TRIGGER IF NOT EXISTS cycle_payload_guard
                BEFORE INSERT ON cycle_plan
                WHEN json_valid(NEW.payload_json) = 0
                  OR json_type(NEW.payload_json) != 'object'
                  OR canonical_json_hash(NEW.payload_json) != NEW.payload_hash
                BEGIN SELECT RAISE(ABORT, 'invalid cycle payload'); END;
                CREATE TRIGGER IF NOT EXISTS long_term_goal_duplicate_revision_guard
                BEFORE INSERT ON long_term_goal
                WHEN EXISTS (
                  SELECT 1 FROM long_term_goal
                  WHERE id = NEW.id AND revision = NEW.revision
                )
                BEGIN SELECT RAISE(ABORT, 'long-term revision already exists'); END;
                CREATE TRIGGER IF NOT EXISTS cycle_plan_duplicate_revision_guard
                BEFORE INSERT ON cycle_plan
                WHEN EXISTS (
                  SELECT 1 FROM cycle_plan
                  WHERE id = NEW.id AND revision = NEW.revision
                )
                BEGIN SELECT RAISE(ABORT, 'cycle revision already exists'); END;
                CREATE TRIGGER IF NOT EXISTS daily_goal_duplicate_revision_guard
                BEFORE INSERT ON daily_goal
                WHEN EXISTS (
                  SELECT 1 FROM daily_goal
                  WHERE id = NEW.id AND revision = NEW.revision
                )
                BEGIN SELECT RAISE(ABORT, 'daily revision already exists'); END;
                CREATE TRIGGER IF NOT EXISTS long_term_goal_immutable_update
                BEFORE UPDATE ON long_term_goal
                BEGIN SELECT RAISE(ABORT, 'long-term revisions are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS long_term_goal_immutable_delete
                BEFORE DELETE ON long_term_goal
                BEGIN SELECT RAISE(ABORT, 'long-term revisions are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS cycle_plan_immutable_update
                BEFORE UPDATE ON cycle_plan
                BEGIN SELECT RAISE(ABORT, 'cycle revisions are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS cycle_plan_immutable_delete
                BEFORE DELETE ON cycle_plan
                BEGIN SELECT RAISE(ABORT, 'cycle revisions are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS daily_goal_immutable_update
                BEFORE UPDATE ON daily_goal
                BEGIN SELECT RAISE(ABORT, 'daily revisions are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS daily_goal_immutable_delete
                BEFORE DELETE ON daily_goal
                BEGIN SELECT RAISE(ABORT, 'daily revisions are immutable'); END;
                DROP TRIGGER IF EXISTS approval_binding_guard;
                DROP TRIGGER IF EXISTS approval_binding_update_guard;
                CREATE TRIGGER approval_binding_guard BEFORE INSERT ON goal_approval
                WHEN EXISTS (
                  SELECT 1 FROM goal_approval WHERE id = NEW.id
                ) OR NOT EXISTS (
                  SELECT 1 FROM daily_goal d
                  WHERE d.id = NEW.daily_goal_id AND d.revision = NEW.daily_revision
                    AND d.long_term_id = NEW.long_term_id
                    AND d.long_term_revision = NEW.long_term_revision
                    AND d.cycle_id = NEW.cycle_id
                    AND d.cycle_revision = NEW.cycle_revision
                    AND d.payload_hash = NEW.payload_hash
                    AND json_extract(d.payload_json, '$.auto_adopt') = NEW.auto_adopt
                ) OR approval_time_valid(NEW.timezone, NEW.expires_at) = 0
                BEGIN SELECT RAISE(ABORT, 'approval binding or time invalid'); END;
                CREATE TRIGGER approval_binding_update_guard
                BEFORE UPDATE OF id, daily_goal_id, daily_revision, long_term_id,
                  long_term_revision, cycle_id, cycle_revision, payload_hash,
                  timezone, expires_at, auto_adopt, created_at ON goal_approval
                BEGIN SELECT RAISE(ABORT, 'approval binding is immutable'); END;
                DROP TRIGGER IF EXISTS approval_lifecycle_update_guard;
                CREATE TRIGGER approval_lifecycle_update_guard
                BEFORE UPDATE OF consumed_at, invalidated_reason ON goal_approval
                WHEN (
                  OLD.consumed_at IS NOT NULL
                  AND NEW.consumed_at IS NOT OLD.consumed_at
                ) OR (
                  OLD.invalidated_reason IS NOT NULL
                  AND NEW.invalidated_reason IS NOT OLD.invalidated_reason
                )
                BEGIN SELECT RAISE(ABORT, 'approval lifecycle is one-way'); END;
                CREATE TRIGGER IF NOT EXISTS approval_binding_delete_guard
                BEFORE DELETE ON goal_approval
                BEGIN SELECT RAISE(ABORT, 'approval binding is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS artifact_duplicate_guard
                BEFORE INSERT ON artifact
                WHEN EXISTS (SELECT 1 FROM artifact WHERE id = NEW.id)
                BEGIN SELECT RAISE(ABORT, 'duplicate artifact'); END;
                CREATE TRIGGER IF NOT EXISTS artifact_immutable_update
                BEFORE UPDATE ON artifact
                BEGIN SELECT RAISE(ABORT, 'artifact is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS artifact_immutable_delete
                BEFORE DELETE ON artifact
                BEGIN SELECT RAISE(ABORT, 'artifact is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS trace_event_duplicate_guard
                BEFORE INSERT ON trace_event
                WHEN EXISTS (
                  SELECT 1 FROM trace_event
                  WHERE run_id = NEW.run_id AND sequence = NEW.sequence
                )
                BEGIN SELECT RAISE(ABORT, 'duplicate trace event'); END;
                CREATE TRIGGER IF NOT EXISTS trace_event_immutable_update
                BEFORE UPDATE ON trace_event
                BEGIN SELECT RAISE(ABORT, 'trace event is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS trace_event_immutable_delete
                BEFORE DELETE ON trace_event
                BEGIN SELECT RAISE(ABORT, 'trace event is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS commit_set_duplicate_guard
                BEFORE INSERT ON commit_set
                WHEN EXISTS (
                  SELECT 1 FROM commit_set
                  WHERE id = NEW.id
                     OR (milestone_id = NEW.milestone_id AND revision = NEW.revision)
                )
                BEGIN SELECT RAISE(ABORT, 'duplicate commit set'); END;
                CREATE TRIGGER IF NOT EXISTS commit_set_immutable_update
                BEFORE UPDATE ON commit_set
                BEGIN SELECT RAISE(ABORT, 'commit set is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS commit_set_immutable_delete
                BEFORE DELETE ON commit_set
                BEGIN SELECT RAISE(ABORT, 'commit set is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS milestone_review_duplicate_guard
                BEFORE INSERT ON milestone_review
                WHEN EXISTS (SELECT 1 FROM milestone_review WHERE id = NEW.id)
                BEGIN SELECT RAISE(ABORT, 'duplicate milestone review'); END;
                CREATE TRIGGER IF NOT EXISTS milestone_review_immutable_update
                BEFORE UPDATE ON milestone_review
                BEGIN SELECT RAISE(ABORT, 'milestone review is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS milestone_review_immutable_delete
                BEFORE DELETE ON milestone_review
                BEGIN SELECT RAISE(ABORT, 'milestone review is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS human_review_duplicate_guard
                BEFORE INSERT ON human_review
                WHEN EXISTS (SELECT 1 FROM human_review WHERE id = NEW.id)
                BEGIN SELECT RAISE(ABORT, 'duplicate human review'); END;
                CREATE TRIGGER IF NOT EXISTS human_review_immutable_update
                BEFORE UPDATE ON human_review
                BEGIN SELECT RAISE(ABORT, 'human review is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS human_review_immutable_delete
                BEFORE DELETE ON human_review
                BEGIN SELECT RAISE(ABORT, 'human review is immutable'); END;
                INSERT OR IGNORE INTO schema_migration(version, applied_at)
                  VALUES (4, CURRENT_TIMESTAMP);
                INSERT OR IGNORE INTO schema_migration(version, applied_at)
                  VALUES (5, CURRENT_TIMESTAMP);
                INSERT OR IGNORE INTO schema_migration(version, applied_at)
                  VALUES (6, CURRENT_TIMESTAMP);
                INSERT OR IGNORE INTO schema_migration(version, applied_at)
                  VALUES (7, CURRENT_TIMESTAMP);
                COMMIT;
                """
            )
            orphan = db.execute(
                """SELECT 1 FROM cycle_plan c LEFT JOIN long_term_goal l
                   ON l.id = c.long_term_id AND l.revision = c.long_term_revision
                   WHERE l.id IS NULL LIMIT 1"""
            ).fetchone()
            inconsistent = db.execute(
                """SELECT 1 FROM daily_goal d LEFT JOIN cycle_plan c
                   ON c.id = d.cycle_id AND c.revision = d.cycle_revision
                   AND c.long_term_id = d.long_term_id
                   AND c.long_term_revision = d.long_term_revision
                   WHERE c.id IS NULL LIMIT 1"""
            ).fetchone()
            if orphan or inconsistent:
                raise RuntimeError("migrated goal parent chain is inconsistent")
            for table, label in (
                ("long_term_goal", "long-term"),
                ("cycle_plan", "cycle"),
            ):
                for row in db.execute(f"SELECT payload_json, payload_hash FROM {table}"):
                    try:
                        payload = json.loads(row["payload_json"])
                    except (TypeError, ValueError, json.JSONDecodeError) as error:
                        raise RuntimeError(f"migrated {label} payload is invalid") from error
                    if not isinstance(payload, dict):
                        raise RuntimeError(f"migrated {label} payload is invalid")
                    if payload_hash(payload) != row["payload_hash"]:
                        raise RuntimeError(f"migrated {label} payload hash mismatch")
            for row in db.execute("SELECT payload_json, payload_hash FROM daily_goal"):
                try:
                    payload = DailyContract.model_validate_json(row["payload_json"]).model_dump(
                        mode="json"
                    )
                except ValueError as error:
                    raise RuntimeError("migrated daily goal contract is invalid") from error
                if payload_hash(payload) != row["payload_hash"]:
                    raise RuntimeError("migrated daily goal hash mismatch")
            invalid_approval = db.execute(
                """SELECT 1 FROM goal_approval a LEFT JOIN daily_goal d
                   ON d.id = a.daily_goal_id AND d.revision = a.daily_revision
                   AND d.long_term_id = a.long_term_id
                   AND d.long_term_revision = a.long_term_revision
                   AND d.cycle_id = a.cycle_id
                   AND d.cycle_revision = a.cycle_revision
                   AND d.payload_hash = a.payload_hash
                   AND json_extract(d.payload_json, '$.auto_adopt') = a.auto_adopt
                   WHERE d.id IS NULL LIMIT 1"""
            ).fetchone()
            if invalid_approval:
                raise RuntimeError("migrated approval binding is inconsistent")
            invalid_approval_time = db.execute(
                """SELECT 1 FROM goal_approval
                   WHERE approval_time_valid(timezone, expires_at) = 0 LIMIT 1"""
            ).fetchone()
            if invalid_approval_time:
                raise RuntimeError("migrated approval time is invalid")

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
                if (
                    not long_term_id
                    or long_term_revision is None
                    or not cycle_id
                    or cycle_revision is None
                ):
                    raise ValueError("daily goal requires long-term and cycle revisions")
                payload = DailyContract.model_validate(payload).model_dump(mode="json")
                encoded = canonical_json(payload)
                digest = payload_hash(payload)
                db.execute(
                    "INSERT INTO daily_goal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
                    (
                        goal_id,
                        revision,
                        long_term_id,
                        long_term_revision,
                        cycle_id,
                        cycle_revision,
                        encoded,
                        digest,
                        now,
                    ),
                )
            db.commit()
        return {
            "id": goal_id,
            "revision": revision,
            "payload_hash": digest,
            "human_review_status": "pending",
        }

    def get_goal(
        self, level: GoalLevel, goal_id: str, revision: int | None = None
    ) -> dict[str, Any] | None:
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

    def list_goal_revisions(self, level: GoalLevel) -> list[dict[str, Any]]:
        table = {"long_term": "long_term_goal", "cycle": "cycle_plan", "daily": "daily_goal"}[
            level
        ]
        with self.connect() as db:
            rows = db.execute(
                f"SELECT id, revision, payload_json, human_review_status "
                f"FROM {table} ORDER BY created_at, id, revision"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "revision": row["revision"],
                "payload": json.loads(row["payload_json"]),
                "human_review_status": row["human_review_status"],
            }
            for row in rows
        ]

    def write_artifact(self, run_id: str | None, kind: str, content: bytes) -> dict[str, Any]:
        if kind not in ARTIFACT_SUFFIXES:
            raise ValueError("artifact kind is not allowlisted")
        content = safe_artifact_content(kind, content)
        artifact_id = str(uuid.uuid4())
        run_key = hashlib.sha256((run_id or "global").encode()).hexdigest()[:16]
        artifact_dir = self.database_path.parent / "artifacts" / run_key
        artifact_dir.mkdir(parents=True, exist_ok=True)
        target = artifact_dir / f"{artifact_id}{ARTIFACT_SUFFIXES[kind]}"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=artifact_dir, delete=False) as output:
                temporary = Path(output.name)
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            digest = hashlib.sha256(content).hexdigest()
            created_at = utc_now().isoformat()
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                os.replace(temporary, target)
                fsync_parent_directory(artifact_dir)
                temporary = None
                db.execute(
                    "INSERT INTO artifact VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                    (artifact_id, run_id, kind, str(target), digest, created_at),
                )
                db.commit()
        except Exception:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise
        return {
            "id": artifact_id,
            "run_id": run_id,
            "kind": kind,
            "path": target,
            "sha256": digest,
            "created_at": created_at,
            "human_review_status": "pending",
        }

    def list_artifacts(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM artifact ORDER BY created_at, id").fetchall()
            statuses = self._latest_human_review_statuses(db, "artifact")
        artifact_root = (self.database_path.parent / "artifacts").resolve()
        expected_paths: set[Path] = set()
        result = []
        for row in rows:
            item = dict(row)
            path = Path(item.pop("path"))
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(artifact_root)
            except (FileNotFoundError, ValueError) as error:
                raise ValueError("artifact integrity verification failed: unsafe path") from error
            expected_name = f"{item['id']}{ARTIFACT_SUFFIXES.get(item['kind'], '')}"
            if resolved.name != expected_name or not resolved.is_file():
                raise ValueError("artifact integrity verification failed: identity mismatch")
            if hashlib.sha256(resolved.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("artifact integrity verification failed: digest mismatch")
            expected_paths.add(resolved)
            item["human_review_status"] = statuses.get(
                item["id"], item["human_review_status"]
            )
            item["integrity_status"] = "verified"
            result.append(item)
        if artifact_root.exists():
            actual_paths = {path.resolve() for path in artifact_root.rglob("*") if path.is_file()}
            if actual_paths != expected_paths:
                raise ValueError("artifact integrity verification failed: orphaned file")
        return result

    def append_trace_event(
        self, run_id: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        allowed = TRACE_PAYLOAD_FIELDS.get(event_type)
        if allowed is None or set(payload) != allowed:
            raise ValueError("trace event type and fields must be allowlisted")
        payload = normalized_trace_payload(event_type, payload)
        encoded = canonical_json(payload)
        created_at = utc_now().isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT sequence, event_hash FROM trace_event WHERE run_id = ? "
                "ORDER BY sequence DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            sequence = int(current["sequence"]) + 1 if current else 1
            previous_hash = str(current["event_hash"]) if current else None
            event_hash = payload_hash(
                {
                    "run_id": run_id,
                    "sequence": sequence,
                    "event_type": event_type,
                    "payload": payload,
                    "previous_hash": previous_hash,
                    "created_at": created_at,
                }
            )
            db.execute(
                "INSERT INTO trace_event VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
                (
                    run_id,
                    sequence,
                    event_type,
                    encoded,
                    previous_hash,
                    event_hash,
                    created_at,
                ),
            )
            db.commit()
        return {
            "run_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "payload": payload,
            "previous_hash": previous_hash,
            "event_hash": event_hash,
            "created_at": created_at,
            "human_review_status": "pending",
        }

    def list_trace_events(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM trace_event ORDER BY run_id, sequence"
            ).fetchall()
        events = []
        previous_by_run: dict[str, tuple[int, str]] = {}
        for row in rows:
            event = dict(row)
            event["payload"] = json.loads(event.pop("payload_json"))
            normalized = normalized_trace_payload(event["event_type"], event["payload"])
            if normalized != event["payload"]:
                raise ValueError("trace integrity verification failed: non-canonical payload")
            previous = previous_by_run.get(event["run_id"])
            expected_sequence = previous[0] + 1 if previous else 1
            expected_previous_hash = previous[1] if previous else None
            if (
                event["sequence"] != expected_sequence
                or event["previous_hash"] != expected_previous_hash
            ):
                raise ValueError("trace integrity verification failed: chain discontinuity")
            expected_hash = payload_hash(
                {
                    "run_id": event["run_id"],
                    "sequence": event["sequence"],
                    "event_type": event["event_type"],
                    "payload": event["payload"],
                    "previous_hash": event["previous_hash"],
                    "created_at": event["created_at"],
                }
            )
            if event["event_hash"] != expected_hash:
                raise ValueError("trace integrity verification failed: digest mismatch")
            event["integrity_status"] = "verified"
            previous_by_run[event["run_id"]] = (event["sequence"], event["event_hash"])
            events.append(event)
        return events

    def freeze_commit_set(
        self, milestone_id: str, revision: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            validated = CommitSetPayload.model_validate(payload)
        except ValueError as error:
            raise ValueError(f"CommitSet payload is invalid: {error}") from error
        if validated.milestone_id != milestone_id or validated.revision != revision:
            raise ValueError("CommitSet identity does not match method arguments")
        payload = validated.model_dump(mode="json")
        commit_set_id = str(uuid.uuid4())
        encoded = canonical_json(payload)
        digest = payload_hash(payload)
        created_at = utc_now().isoformat()
        with self.connect() as db:
            db.execute(
                "INSERT INTO commit_set VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (commit_set_id, milestone_id, revision, encoded, digest, created_at),
            )
        return {
            "id": commit_set_id,
            "milestone_id": milestone_id,
            "revision": revision,
            "payload": payload,
            "payload_hash": digest,
            "created_at": created_at,
            "human_review_status": "pending",
        }

    def record_milestone_review(
        self,
        milestone_id: str,
        commit_set_id: str,
        verdict: str,
        findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if verdict not in {"passed", "passed_with_findings", "failed", "blocked"}:
            raise ValueError("invalid milestone review verdict")
        review_id = str(uuid.uuid4())
        encoded = canonical_json(findings)
        created_at = utc_now().isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            commit_set = db.execute(
                "SELECT milestone_id FROM commit_set WHERE id = ?", (commit_set_id,)
            ).fetchone()
            if commit_set is None or commit_set["milestone_id"] != milestone_id:
                db.rollback()
                raise ValueError("milestone review requires a matching CommitSet")
            db.execute(
                "INSERT INTO milestone_review VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (review_id, milestone_id, commit_set_id, verdict, encoded, created_at),
            )
            db.commit()
        return {
            "id": review_id,
            "milestone_id": milestone_id,
            "commit_set_id": commit_set_id,
            "verdict": verdict,
            "findings": findings,
            "created_at": created_at,
            "human_review_status": "pending",
        }

    def submit_human_review(
        self, subject_type: str, subject_id: str, status: str, comment: str
    ) -> dict[str, Any]:
        table = HUMAN_REVIEW_SUBJECTS.get(subject_type)
        if table is None:
            raise ValueError("human review subject type is not allowlisted")
        if status not in {"approved", "rejected"}:
            raise ValueError("human review status must be approved or rejected")
        review_id = str(uuid.uuid4())
        created_at = utc_now().isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(f"SELECT 1 FROM {table} WHERE id = ?", (subject_id,)).fetchone() is None:
                db.rollback()
                raise ValueError("human review subject does not exist")
            db.execute(
                "INSERT INTO human_review VALUES (?, ?, ?, ?, ?, ?)",
                (review_id, subject_type, subject_id, status, comment, created_at),
            )
            db.commit()
        return {
            "id": review_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "status": status,
            "comment": comment,
            "created_at": created_at,
        }

    def list_commit_sets(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM commit_set ORDER BY milestone_id, revision"
            ).fetchall()
            statuses = self._latest_human_review_statuses(db, "commit_set")
        result = []
        for row in rows:
            item = dict(row)
            payload = json.loads(item.pop("payload_json"))
            if payload_hash(payload) != item["payload_hash"]:
                raise ValueError("CommitSet integrity verification failed: digest mismatch")
            if payload.get("schema_version") == 1:
                try:
                    validated = CommitSetPayload.model_validate(payload)
                except ValueError as error:
                    raise ValueError("CommitSet integrity verification failed: schema") from error
                if (
                    validated.milestone_id != item["milestone_id"]
                    or validated.revision != item["revision"]
                ):
                    raise ValueError("CommitSet integrity verification failed: identity")
                item["payload"] = validated.model_dump(mode="json")
                item["integrity_status"] = "verified"
            else:
                item["payload"] = None
                item["integrity_status"] = "legacy_unverified"
            item["human_review_status"] = statuses.get(
                item["id"], item["human_review_status"]
            )
            result.append(item)
        return result

    def list_milestone_reviews(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM milestone_review ORDER BY created_at, id"
            ).fetchall()
            statuses = self._latest_human_review_statuses(db, "milestone_review")
        result = []
        for row in rows:
            item = dict(row)
            item["findings"] = json.loads(item.pop("findings_json"))
            item["human_review_status"] = statuses.get(
                item["id"], item["human_review_status"]
            )
            result.append(item)
        return result

    def list_human_reviews(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM human_review ORDER BY created_at, id").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _latest_human_review_statuses(
        db: sqlite3.Connection, subject_type: str
    ) -> dict[str, str]:
        rows = db.execute(
            "SELECT subject_id, status FROM human_review WHERE subject_type = ? "
            "ORDER BY created_at, id",
            (subject_type,),
        ).fetchall()
        return {str(row["subject_id"]): str(row["status"]) for row in rows}

    def approve_daily_goal(
        self,
        daily_goal_id: str,
        daily_revision: int,
        timezone: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        now = utc_now()
        expires_at = parse_approval_expiry(timezone, expires_at.isoformat())
        if expires_at <= now:
            raise ValueError("approval expiry must be in the future")
        approval_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            daily_row = db.execute(
                "SELECT * FROM daily_goal WHERE id = ? AND revision = ?",
                (daily_goal_id, daily_revision),
            ).fetchone()
            if daily_row is None:
                raise ValueError("daily goal revision not found")
            daily = dict(daily_row)
            daily["payload"] = json.loads(daily.pop("payload_json"))
            daily["payload"] = DailyContract.model_validate(daily["payload"]).model_dump(
                mode="json"
            )
            if payload_hash(daily["payload"]) != daily["payload_hash"]:
                raise ValueError("daily goal payload hash mismatch")
            latest_long = db.execute(
                "SELECT MAX(revision) AS revision FROM long_term_goal WHERE id = ?",
                (daily["long_term_id"],),
            ).fetchone()["revision"]
            latest_cycle = db.execute(
                "SELECT MAX(revision) AS revision FROM cycle_plan WHERE id = ?",
                (daily["cycle_id"],),
            ).fetchone()["revision"]
            latest_daily = db.execute(
                "SELECT MAX(revision) AS revision FROM daily_goal WHERE id = ?",
                (daily_goal_id,),
            ).fetchone()["revision"]
            if latest_daily != daily_revision:
                raise ValueError("daily goal revision is stale")
            if (
                latest_long != daily["long_term_revision"]
                or latest_cycle != daily["cycle_revision"]
            ):
                raise ValueError("daily goal parent revision is stale")
            db.execute(
                """INSERT INTO goal_approval (
                    id, daily_goal_id, daily_revision, long_term_id, long_term_revision,
                    cycle_id, cycle_revision,
                    payload_hash, timezone, expires_at, auto_adopt, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval_id,
                    daily_goal_id,
                    daily_revision,
                    daily["long_term_id"],
                    daily["long_term_revision"],
                    daily["cycle_id"],
                    daily["cycle_revision"],
                    daily["payload_hash"],
                    timezone,
                    expires_at.isoformat(),
                    int(bool(daily["payload"]["auto_adopt"])),
                    now.isoformat(),
                ),
            )
            db.commit()
        return {
            "approval_id": approval_id,
            "daily_goal_id": daily_goal_id,
            "daily_revision": daily_revision,
            "payload_hash": daily["payload_hash"],
            "expires_at": expires_at.isoformat(),
            "human_review_status": "pending",
        }

    def _approval_reason(
        self, db: sqlite3.Connection, approval_id: str, now: datetime
    ) -> str | None:
        approval = db.execute("SELECT * FROM goal_approval WHERE id = ?", (approval_id,)).fetchone()
        if approval is None:
            return "not_found"
        daily = db.execute(
            "SELECT * FROM daily_goal WHERE id = ? AND revision = ?",
            (approval["daily_goal_id"], approval["daily_revision"]),
        ).fetchone()
        if daily is None:
            return "daily_revision_missing"
        try:
            canonical_daily = DailyContract.model_validate_json(daily["payload_json"]).model_dump(
                mode="json"
            )
        except ValueError:
            return "daily_contract_invalid"
        latest_daily = db.execute(
            "SELECT MAX(revision) AS revision FROM daily_goal WHERE id = ?",
            (approval["daily_goal_id"],),
        ).fetchone()["revision"]
        latest_long = db.execute(
            "SELECT MAX(revision) AS revision FROM long_term_goal WHERE id = ?",
            (approval["long_term_id"],),
        ).fetchone()["revision"]
        latest_cycle = db.execute(
            "SELECT MAX(revision) AS revision FROM cycle_plan WHERE id = ?",
            (approval["cycle_id"],),
        ).fetchone()["revision"]
        reason = None
        if approval["invalidated_reason"] is not None:
            reason = str(approval["invalidated_reason"])
        elif approval["consumed_at"]:
            reason = "consumed"
        else:
            try:
                approval_expiry = parse_approval_expiry(
                    approval["timezone"], approval["expires_at"]
                )
            except ValueError:
                reason = "approval_time_invalid"
            else:
                if approval_expiry <= now:
                    reason = "expired"
        if reason is None and latest_daily != approval["daily_revision"]:
            reason = "daily_revision_changed"
        elif reason is None and (
            daily["long_term_id"] != approval["long_term_id"]
            or daily["cycle_id"] != approval["cycle_id"]
        ):
            reason = "parent_identity_changed"
        elif reason is None and daily["long_term_revision"] != approval["long_term_revision"]:
            reason = "long_term_binding_changed"
        elif reason is None and daily["cycle_revision"] != approval["cycle_revision"]:
            reason = "cycle_binding_changed"
        elif reason is None and latest_long != approval["long_term_revision"]:
            reason = "long_term_revision_changed"
        elif reason is None and latest_cycle != approval["cycle_revision"]:
            reason = "cycle_revision_changed"
        elif reason is None and payload_hash(canonical_daily) != daily["payload_hash"]:
            reason = "payload_hash_mismatch"
        elif reason is None and daily["payload_hash"] != approval["payload_hash"]:
            reason = "payload_changed"
        return reason

    def validate_approval(self, approval_id: str, now: datetime | None = None) -> dict[str, Any]:
        now = normalized_utc(now or utc_now())
        with self.connect() as db:
            reason = self._approval_reason(db, approval_id, now)
        return {"valid": reason is None, "reason": reason, "approval_id": approval_id}

    def consume_approval(self, approval_id: str, consumed_at: datetime | None = None) -> bool:
        consumed_at = normalized_utc(consumed_at or utc_now())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._approval_reason(db, approval_id, consumed_at) is not None:
                db.rollback()
                return False
            result = db.execute(
                "UPDATE goal_approval SET consumed_at = ? WHERE id = ? AND consumed_at IS NULL",
                (consumed_at.isoformat(), approval_id),
            )
            db.commit()
        return result.rowcount == 1

    def acquire_lease(
        self,
        task_id: str,
        milestone_id: str,
        owner_run_id: str,
        worker_fingerprint: str,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        now = normalized_utc(now)
        expires_at = normalized_utc(expires_at)
        if expires_at <= now:
            raise ValueError("lease expiry must be after acquisition")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT * FROM execution_lease WHERE task_id = ?", (task_id,)
            ).fetchone()
            if (
                current
                and datetime.fromisoformat(current["expires_at"]) > now
                and (
                    current["owner_run_id"] != owner_run_id
                    or current["milestone_id"] != milestone_id
                    or current["worker_fingerprint"] != worker_fingerprint
                )
            ):
                db.rollback()
                return False
            if (
                current
                and datetime.fromisoformat(current["expires_at"]) > now
                and (
                    now <= datetime.fromisoformat(current["heartbeat_at"])
                    or expires_at <= datetime.fromisoformat(current["expires_at"])
                )
            ):
                db.rollback()
                return False
            db.execute(
                "INSERT OR REPLACE INTO execution_lease VALUES (?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    milestone_id,
                    owner_run_id,
                    now.isoformat(),
                    expires_at.isoformat(),
                    worker_fingerprint,
                ),
            )
            db.commit()
        return True

    def release_lease(
        self,
        task_id: str,
        milestone_id: str,
        owner_run_id: str,
        worker_fingerprint: str,
    ) -> bool:
        with self.connect() as db:
            result = db.execute(
                """DELETE FROM execution_lease WHERE task_id = ? AND milestone_id = ?
                   AND owner_run_id = ? AND worker_fingerprint = ?""",
                (task_id, milestone_id, owner_run_id, worker_fingerprint),
            )
        return result.rowcount == 1

    def heartbeat_lease(
        self,
        task_id: str,
        milestone_id: str,
        owner_run_id: str,
        worker_fingerprint: str,
        heartbeat_at: datetime,
        expires_at: datetime,
    ) -> bool:
        heartbeat_at = normalized_utc(heartbeat_at)
        expires_at = normalized_utc(expires_at)
        if expires_at <= heartbeat_at:
            raise ValueError("lease expiry must be after heartbeat")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                """SELECT * FROM execution_lease WHERE task_id = ? AND milestone_id = ?
                   AND owner_run_id = ? AND worker_fingerprint = ?""",
                (task_id, milestone_id, owner_run_id, worker_fingerprint),
            ).fetchone()
            if (
                current is None
                or datetime.fromisoformat(current["expires_at"]) <= heartbeat_at
                or heartbeat_at <= datetime.fromisoformat(current["heartbeat_at"])
                or expires_at <= datetime.fromisoformat(current["expires_at"])
            ):
                db.rollback()
                return False
            result = db.execute(
                """UPDATE execution_lease SET heartbeat_at = ?, expires_at = ?
                   WHERE task_id = ? AND milestone_id = ? AND owner_run_id = ?
                     AND worker_fingerprint = ?""",
                (
                    heartbeat_at.isoformat(),
                    expires_at.isoformat(),
                    task_id,
                    milestone_id,
                    owner_run_id,
                    worker_fingerprint,
                ),
            )
            db.commit()
        return result.rowcount == 1

    def get_lease(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM execution_lease WHERE task_id = ?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_run(self, daily_goal_id: str, daily_revision: int) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        now = utc_now().isoformat()
        with self.connect() as db:
            db.execute(
                "INSERT INTO run VALUES (?, ?, ?, NULL, 'pending', ?, ?, 'pending')",
                (run_id, daily_goal_id, daily_revision, now, now),
            )
        return {"id": run_id, "state": "pending", "human_review_status": "pending"}

    def transition_run(self, run_id: str, expected: str, target: str) -> dict[str, Any]:
        validate_transition(expected, target)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "UPDATE run SET state = ?, updated_at = ? WHERE id = ? AND state = ?",
                (target, utc_now().isoformat(), run_id, expected),
            )
            if result.rowcount != 1:
                db.rollback()
                raise ValueError("run state changed or run not found")
            db.commit()
        return {"id": run_id, "state": target, "human_review_status": "pending"}
