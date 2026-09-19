from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone

from writing_ops.service import WritingOpsService
from writing_ops.state import DAILY_REQUIRED, StateStore


def daily_payload(now: datetime) -> dict[str, object]:
    payload: dict[str, object] = {key: f"value-{key}" for key in DAILY_REQUIRED}
    payload.update(
        {
            "must_happen": ["turning point"],
            "must_not_happen": ["external publication"],
            "forbidden_zones": ["canon rewrite"],
            "word_count": 1800,
            "auto_adopt": False,
            "window_start": (now - timedelta(hours=1)).isoformat(),
            "window_end": (now + timedelta(hours=1)).isoformat(),
        }
    )
    return payload


def test_run_due_claim_poll_and_reconcile_require_approval_lease_and_token(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    service = WritingOpsService(store=store)
    now = datetime.now(UTC).replace(microsecond=0)
    long_term = store.upsert_goal("long_term", {"objective": "book"})
    cycle = store.upsert_goal(
        "cycle",
        {"objective": "arc"},
        long_term_id=long_term["id"],
        long_term_revision=long_term["revision"],
    )
    daily = store.upsert_goal(
        "daily",
        daily_payload(now),
        long_term_id=long_term["id"],
        long_term_revision=long_term["revision"],
        cycle_id=cycle["id"],
        cycle_revision=cycle["revision"],
    )
    run = store.create_run(daily["id"], daily["revision"])

    assert service.run_due("claim", run["id"], now=now)["reason"] == "approval_unavailable"
    approval = store.approve_daily_goal(
        daily["id"], daily["revision"], "Asia/Shanghai", now + timedelta(hours=1)
    )
    claimed = service.run_due("claim", run["id"], now=now)
    token = claimed.pop("resume_token")

    assert claimed == {
        "status": "claimed",
        "run_id": run["id"],
        "state": "claimed",
        "next_action": "poll",
        "human_review_status": "pending",
    }
    with store.connect() as db:
        bound_run = db.execute("SELECT approval_id FROM run WHERE id = ?", (run["id"],)).fetchone()
        resume = db.execute(
            "SELECT token_hash FROM run_resume WHERE run_id = ?", (run["id"],)
        ).fetchone()
    assert bound_run["approval_id"] == approval["approval_id"]
    assert resume["token_hash"] != token

    assert service.run_due("poll", run["id"], "wrong", now=now + timedelta(seconds=30)) == {
        "status": "manual_reconcile",
        "run_id": run["id"],
        "state": "claimed",
        "reason": "resume_token_invalid",
        "human_review_status": "pending",
    }
    assert service.run_due("reconcile", run["id"], now=now + timedelta(seconds=30))[
        "reason"
    ] == "resume_token_required"
    assert service.run_due("reconcile", run["id"], token, now=now + timedelta(seconds=30))[
        "status"
    ] == "resume_available"
    polled = service.run_due("poll", run["id"], token, now=now + timedelta(seconds=30))
    assert polled["next_action"] == "submit_review"
    assert WritingOpsService(store=store).run_due(
        "poll", run["id"], token, now=now + timedelta(seconds=45)
    )["reason"] == "lease_owned_by_other_worker"
    recovered = WritingOpsService(store=store).run_due(
        "poll", run["id"], token, now=now + timedelta(minutes=3)
    )
    assert recovered["status"] == "claimed"
    assert recovered["next_action"] == "submit_review"

    store.transition_run(run["id"], "claimed", "running")
    lease_before = store.get_lease(f"writing_run_due:{run['id']}")
    rejected = WritingOpsService(store=store).run_due(
        "poll", run["id"], token, now=now + timedelta(minutes=6)
    )
    assert rejected["reason"] == "run_not_claimed"
    assert store.get_lease(f"writing_run_due:{run['id']}") == lease_before

    second_run = store.create_run(daily["id"], daily["revision"])
    assert service.run_due("claim", second_run["id"], now=now)["reason"] == "approval_unavailable"
    store.approve_daily_goal(
        daily["id"], daily["revision"], "Asia/Shanghai", now + timedelta(hours=1)
    )
    second_claim = service.run_due("claim", second_run["id"], now=now)
    second_token = second_claim["resume_token"]
    with store.connect() as db:
        db.execute(
            """INSERT INTO step (id, run_id, kind, state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "existing-step", second_run["id"], "generate", "unknown_outcome",
                now.isoformat(), now.isoformat(),
            ),
        )
    second_lease = store.get_lease(f"writing_run_due:{second_run['id']}")
    assert service.run_due("poll", second_run["id"], second_token, now=now + timedelta(seconds=30))[
        "reason"
    ] == "step_exists"
    reconciled = service.run_due(
        "reconcile", second_run["id"], second_token, now=now + timedelta(minutes=3)
    )
    assert reconciled["reason"] == "step_exists"
    assert store.get_lease(f"writing_run_due:{second_run['id']}") == second_lease

    other_daily = store.upsert_goal(
        "daily",
        daily_payload(now),
        long_term_id=long_term["id"],
        long_term_revision=long_term["revision"],
        cycle_id=cycle["id"],
        cycle_revision=cycle["revision"],
    )
    other_approval = store.approve_daily_goal(
        other_daily["id"], other_daily["revision"], "Asia/Shanghai", now + timedelta(hours=1)
    )
    third_run = store.create_run(daily["id"], daily["revision"])
    with store.connect() as db:
        db.execute(
            "UPDATE run SET approval_id = ? WHERE id = ?",
            (other_approval["approval_id"], third_run["id"]),
        )
    assert service.run_due("claim", third_run["id"], now=now)["reason"] == "approval_unavailable"
    assert store.get_lease(f"writing_run_due:{third_run['id']}") is None


def test_run_due_respects_daily_window_at_claim_and_resume(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    service = WritingOpsService(store=store)
    now = datetime.now(UTC).replace(microsecond=0)
    long_term = store.upsert_goal("long_term", {"objective": "book"})
    cycle = store.upsert_goal(
        "cycle", {"objective": "arc"},
        long_term_id=long_term["id"], long_term_revision=long_term["revision"],
    )
    window_start = (now + timedelta(days=1)).astimezone(timezone(timedelta(hours=8)))
    window_end = window_start + timedelta(hours=1)
    payload = daily_payload(now)
    payload.update(window_start=window_start.isoformat(), window_end=window_end.isoformat())
    daily = store.upsert_goal(
        "daily", payload,
        long_term_id=long_term["id"], long_term_revision=long_term["revision"],
        cycle_id=cycle["id"], cycle_revision=cycle["revision"],
    )
    store.approve_daily_goal(
        daily["id"], daily["revision"], "Asia/Shanghai", window_end + timedelta(hours=1)
    )
    run = store.create_run(daily["id"], daily["revision"])
    assert service.run_due("claim", run["id"], now=now)["reason"] == "window_not_open"
    with store.connect() as db:
        assert db.execute("SELECT state FROM run WHERE id = ?", (run["id"],)).fetchone()[
            "state"
        ] == "pending"
    assert store.get_lease(f"writing_run_due:{run['id']}") is None

    claimed = service.run_due("claim", run["id"], now=window_start)
    assert claimed["status"] == "claimed"
    token = claimed["resume_token"]
    assert service.run_due(
        "poll", run["id"], token, now=window_start + timedelta(seconds=30)
    )["status"] == "claimed"
    lease_before = store.get_lease(f"writing_run_due:{run['id']}")
    assert service.run_due("poll", run["id"], token, now=window_end)["reason"] == "window_closed"
    assert service.run_due("reconcile", run["id"], token, now=window_end)[
        "reason"
    ] == "window_closed"
    assert store.get_lease(f"writing_run_due:{run['id']}") == lease_before

    expired_payload = daily_payload(now)
    expired_payload.update(
        window_start=(now - timedelta(hours=3)).isoformat(),
        window_end=(now - timedelta(hours=2)).isoformat(),
    )
    expired_daily = store.upsert_goal(
        "daily", expired_payload,
        long_term_id=long_term["id"], long_term_revision=long_term["revision"],
        cycle_id=cycle["id"], cycle_revision=cycle["revision"],
    )
    store.approve_daily_goal(
        expired_daily["id"], expired_daily["revision"],
        "Asia/Shanghai", now + timedelta(hours=1),
    )
    expired_run = store.create_run(expired_daily["id"], expired_daily["revision"])
    assert service.run_due("claim", expired_run["id"], now=now)["reason"] == "window_closed"


def test_run_due_claim_is_unique_per_approval_under_concurrency(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    service = WritingOpsService(store=store)
    now = datetime.now(UTC).replace(microsecond=0)
    long_term = store.upsert_goal("long_term", {"objective": "book"})
    cycle = store.upsert_goal(
        "cycle", {"objective": "arc"},
        long_term_id=long_term["id"], long_term_revision=long_term["revision"],
    )
    daily = store.upsert_goal(
        "daily", daily_payload(now),
        long_term_id=long_term["id"], long_term_revision=long_term["revision"],
        cycle_id=cycle["id"], cycle_revision=cycle["revision"],
    )
    store.approve_daily_goal(
        daily["id"], daily["revision"], "Asia/Shanghai", now + timedelta(hours=1)
    )
    runs = [store.create_run(daily["id"], daily["revision"]) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda run: service.run_due("claim", run["id"], now=now), runs))
    assert sorted(result["status"] for result in results) == ["blocked", "claimed"]
    assert [result.get("reason") for result in results if result["status"] == "blocked"] == [
        "approval_unavailable"
    ]
    assert sum(store.get_lease(f"writing_run_due:{run['id']}") is not None for run in runs) == 1

    claimed = next(result for result in results if result["status"] == "claimed")
    duplicate_run = store.create_run(daily["id"], daily["revision"])
    with store.connect() as db:
        approval_id = db.execute(
            "SELECT approval_id FROM run WHERE id = ?", (claimed["run_id"],)
        ).fetchone()["approval_id"]
        db.execute(
            "UPDATE run SET approval_id = ? WHERE id = ?", (approval_id, duplicate_run["id"])
        )
    lease_before = store.get_lease(f"writing_run_due:{claimed['run_id']}")
    assert service.run_due(
        "poll", claimed["run_id"], claimed["resume_token"], now=now + timedelta(seconds=30)
    )["reason"] == "approval_unavailable"
    assert store.get_lease(f"writing_run_due:{claimed['run_id']}") == lease_before
