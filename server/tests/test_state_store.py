from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from writing_ops.state import DAILY_REQUIRED, TABLES, StateStore, validate_transition


def daily_payload() -> dict[str, object]:
    payload: dict[str, object] = {key: f"value-{key}" for key in DAILY_REQUIRED}
    payload.update(
        {
            "must_happen": ["turning point"],
            "must_not_happen": ["external publication"],
            "forbidden_zones": ["canon rewrite"],
            "word_count": 1800,
            "auto_adopt": False,
        }
    )
    return payload


def test_migration_creates_every_core_table(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    assert set(TABLES) <= store.table_names()


def test_goal_revisions_are_immutable_and_daily_contract_is_complete(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    long_term = store.upsert_goal("long_term", {"objective": "complete book"})
    changed = store.upsert_goal(
        "long_term", {"objective": "complete revised book"}, goal_id=long_term["id"]
    )
    cycle = store.upsert_goal(
        "cycle",
        {"objective": "finish arc"},
        long_term_id=long_term["id"],
        long_term_revision=changed["revision"],
    )
    daily = store.upsert_goal(
        "daily",
        daily_payload(),
        long_term_id=long_term["id"],
        long_term_revision=changed["revision"],
        cycle_id=cycle["id"],
        cycle_revision=cycle["revision"],
    )

    assert long_term["revision"] == 1
    assert changed["revision"] == 2
    assert daily["revision"] == 1
    assert daily["human_review_status"] == "pending"
    with pytest.raises(ValueError, match="missing required"):
        store.upsert_goal(
            "daily",
            {"project": "only one field"},
            long_term_id=long_term["id"],
            long_term_revision=changed["revision"],
            cycle_id=cycle["id"],
            cycle_revision=cycle["revision"],
        )


def test_execution_lease_prevents_takeover_until_expiry(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    now = datetime(2026, 9, 2, tzinfo=UTC)
    assert store.acquire_lease("task", "M1", "run-a", "worker-a", now, now + timedelta(minutes=2))
    assert not store.acquire_lease(
        "task", "M1", "run-b", "worker-b", now + timedelta(seconds=30), now + timedelta(minutes=3)
    )
    assert store.heartbeat_lease(
        "task", "run-a", now + timedelta(minutes=1), now + timedelta(minutes=3)
    )
    assert store.get_lease("task")["worker_fingerprint"] == "worker-a"
    assert store.acquire_lease(
        "task", "M1", "run-b", "worker-b", now + timedelta(minutes=4), now + timedelta(minutes=6)
    )
    assert not store.release_lease("task", "run-a")
    assert store.release_lease("task", "run-b")


def test_approval_is_bound_to_all_goal_revisions_and_expiry(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    long_term = store.upsert_goal("long_term", {"objective": "complete book"})
    cycle = store.upsert_goal(
        "cycle",
        {"objective": "finish arc"},
        long_term_id=long_term["id"],
        long_term_revision=long_term["revision"],
    )
    daily = store.upsert_goal(
        "daily",
        daily_payload(),
        long_term_id=long_term["id"],
        long_term_revision=long_term["revision"],
        cycle_id=cycle["id"],
        cycle_revision=cycle["revision"],
    )
    approval = store.approve_daily_goal(
        daily["id"], daily["revision"], "Asia/Shanghai", datetime.now(UTC) + timedelta(hours=1)
    )
    assert store.validate_approval(approval["approval_id"])["valid"] is True

    store.upsert_goal(
        "long_term", {"objective": "changed"}, goal_id=long_term["id"]
    )
    invalid = store.validate_approval(approval["approval_id"])
    assert invalid == {
        "valid": False,
        "reason": "long_term_revision_changed",
        "approval_id": approval["approval_id"],
    }


def test_run_state_machine_rejects_skips_and_terminal_replay() -> None:
    validate_transition("pending", "claimed")
    validate_transition("running", "reconciling")
    with pytest.raises(ValueError, match="invalid run transition"):
        validate_transition("pending", "completed")
    with pytest.raises(ValueError, match="invalid run transition"):
        validate_transition("completed", "running")
