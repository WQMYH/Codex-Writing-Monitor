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
            "window_start": "2026-09-02T09:00:00+08:00",
            "window_end": "2026-09-02T11:00:00+08:00",
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
    with pytest.raises(ValueError):
        store.upsert_goal(
            "daily",
            {"project": "only one field"},
            long_term_id=long_term["id"],
            long_term_revision=changed["revision"],
            cycle_id=cycle["id"],
            cycle_revision=cycle["revision"],
        )
    malformed = daily_payload()
    malformed["auto_adopt"] = "false"
    with pytest.raises(ValueError):
        store.upsert_goal(
            "daily",
            malformed,
            long_term_id=long_term["id"],
            long_term_revision=changed["revision"],
            cycle_id=cycle["id"],
            cycle_revision=cycle["revision"],
        )

    unrelated = store.upsert_goal("long_term", {"objective": "other"})
    with pytest.raises(Exception, match="inconsistent daily parent chain"):
        store.upsert_goal(
            "daily",
            daily_payload(),
            long_term_id=unrelated["id"],
            long_term_revision=unrelated["revision"],
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
    with pytest.raises(ValueError, match="after acquisition"):
        store.acquire_lease("bad", "M1", "run", "worker", now, now)
    with pytest.raises(ValueError, match="after heartbeat"):
        store.heartbeat_lease("task", "run", now, now)


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
        "daily",
        daily_payload(),
        goal_id=daily["id"],
        long_term_id=long_term["id"],
        long_term_revision=long_term["revision"],
        cycle_id=cycle["id"],
        cycle_revision=cycle["revision"],
    )
    assert store.validate_approval(approval["approval_id"])["reason"] == "daily_revision_changed"
    with pytest.raises(ValueError, match="stale"):
        store.approve_daily_goal(
            daily["id"],
            daily["revision"],
            "Asia/Shanghai",
            datetime.now(UTC) + timedelta(hours=1),
        )

    fresh_daily = store.get_goal("daily", daily["id"])
    fresh_approval = store.approve_daily_goal(
        fresh_daily["id"],
        fresh_daily["revision"],
        "Asia/Shanghai",
        datetime.now(UTC) + timedelta(hours=1),
    )

    store.upsert_goal(
        "long_term", {"objective": "changed"}, goal_id=long_term["id"]
    )
    invalid = store.validate_approval(fresh_approval["approval_id"])
    assert invalid == {
        "valid": False,
        "reason": "long_term_revision_changed",
        "approval_id": fresh_approval["approval_id"],
    }

    isolated_store = StateStore(tmp_path / "isolated.sqlite3")
    isolated_long = isolated_store.upsert_goal("long_term", {"objective": "book"})
    isolated_cycle = isolated_store.upsert_goal(
        "cycle",
        {"objective": "arc"},
        long_term_id=isolated_long["id"],
        long_term_revision=isolated_long["revision"],
    )
    isolated_daily = isolated_store.upsert_goal(
        "daily",
        daily_payload(),
        long_term_id=isolated_long["id"],
        long_term_revision=isolated_long["revision"],
        cycle_id=isolated_cycle["id"],
        cycle_revision=isolated_cycle["revision"],
    )
    with pytest.raises(ValueError, match="timezone"):
        isolated_store.approve_daily_goal(
            isolated_daily["id"],
            isolated_daily["revision"],
            "Not/AZone",
            datetime.now(UTC) + timedelta(hours=1),
        )
    consumable = isolated_store.approve_daily_goal(
        isolated_daily["id"],
        isolated_daily["revision"],
        "Asia/Shanghai",
        datetime.now(UTC) + timedelta(hours=1),
    )
    assert isolated_store.validate_approval(
        consumable["approval_id"], datetime.now(UTC) + timedelta(hours=2)
    )["reason"] == "expired"
    assert isolated_store.consume_approval(consumable["approval_id"])
    assert isolated_store.validate_approval(consumable["approval_id"])["reason"] == "consumed"


def test_run_state_machine_rejects_skips_and_terminal_replay() -> None:
    validate_transition("pending", "claimed")
    validate_transition("running", "reconciling")
    with pytest.raises(ValueError, match="invalid run transition"):
        validate_transition("pending", "completed")
    with pytest.raises(ValueError, match="invalid run transition"):
        validate_transition("completed", "running")


def test_persisted_run_transition_is_compare_and_swap(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    run = store.create_run("daily", 1)
    assert store.transition_run(run["id"], "pending", "claimed")["state"] == "claimed"
    with pytest.raises(ValueError, match="state changed"):
        store.transition_run(run["id"], "pending", "cancelled")
    with pytest.raises(ValueError, match="invalid run transition"):
        store.transition_run(run["id"], "claimed", "completed")
