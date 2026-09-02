from __future__ import annotations

import hashlib
import sqlite3

import pytest

from writing_ops.service import WritingOpsService
from writing_ops.state import DAILY_REQUIRED, StateStore


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


def test_dashboard_view_model_uses_real_three_level_goal_state(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    long_term = store.upsert_goal("long_term", {"objective": "finish the novel"})
    cycle = store.upsert_goal(
        "cycle",
        {"objective": "complete the first arc"},
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

    view_model = WritingOpsService(store=store).dashboard()

    assert view_model.schema_version == 2
    assert view_model.milestone == "M2"
    assert view_model.milestone_state == "implementing"
    assert [goal.id for goal in view_model.creator.goals.long_term] == [long_term["id"]]
    assert [goal.id for goal in view_model.creator.goals.cycle] == [cycle["id"]]
    assert [goal.id for goal in view_model.creator.goals.daily] == [daily["id"]]
    assert view_model.creator.goals.daily[0].payload["chapter"] == "value-chapter"
    assert view_model.creator.human_review_status == "pending"
    assert view_model.reviewer.human_review_status == "pending"
    assert "创作者模式" in view_model.text_dashboard
    assert "审查模式" in view_model.text_dashboard


def test_artifacts_and_allowlisted_hash_chained_trace_feed_the_shared_view_model(
    tmp_path,
) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    run = store.create_run("daily", 1)

    artifact = store.write_artifact(run["id"], "candidate_text", b"complete candidate")
    intent = store.append_trace_event(
        run["id"],
        "step_intent",
        {"step_id": "generate-1", "kind": "generate", "state": "dispatched"},
    )
    ack = store.append_trace_event(
        run["id"],
        "step_ack",
        {"step_id": "generate-1", "outcome": "durable_ack", "state": "completed"},
    )

    assert artifact["sha256"] == hashlib.sha256(b"complete candidate").hexdigest()
    assert artifact["path"].read_bytes() == b"complete candidate"
    assert artifact["human_review_status"] == "pending"
    assert intent["sequence"] == 1
    assert ack["sequence"] == 2
    assert ack["previous_hash"] == intent["event_hash"]
    with pytest.raises(ValueError, match="allowlisted"):
        store.append_trace_event(
            run["id"],
            "step_ack",
            {"step_id": "generate-1", "authorization": "Bearer secret"},
        )

    view_model = WritingOpsService(store=store).dashboard()
    assert [item.id for item in view_model.creator.artifacts] == [artifact["id"]]
    assert [item.sequence for item in view_model.reviewer.trace_events] == [1, 2]
    assert all(
        item.human_review_status == "pending" for item in view_model.reviewer.trace_events
    )
    assert artifact["id"] in view_model.text_dashboard
    assert "step_ack#2" in view_model.text_dashboard


def test_commit_set_and_review_state_are_projected_and_human_decisions_are_explicit(
    tmp_path,
) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    commit_set = store.freeze_commit_set(
        "M2", 1, {"repositories": {"writingOps": "0123456789abcdef"}}
    )
    milestone_review = store.record_milestone_review(
        "M2",
        commit_set["id"],
        "passed_with_findings",
        [{"id": "M2-MINOR", "severity": "minor", "status": "open"}],
    )

    decision = WritingOpsService(store=store).human_review_submit(
        "commit_set", commit_set["id"], "approved", "accept this exact revision"
    )
    view_model = WritingOpsService(store=store).dashboard()

    assert decision["subject_id"] == commit_set["id"]
    assert decision["status"] == "approved"
    assert view_model.reviewer.commit_sets[0].human_review_status == "approved"
    assert view_model.reviewer.milestone_reviews[0].id == milestone_review["id"]
    assert view_model.reviewer.milestone_reviews[0].human_review_status == "pending"
    assert view_model.reviewer.human_reviews[0].comment == "accept this exact revision"
    assert commit_set["id"] in view_model.text_dashboard
    assert "passed_with_findings" in view_model.text_dashboard
    with pytest.raises(ValueError, match="subject type"):
        WritingOpsService(store=store).human_review_submit(
            "sqlite_master", "anything", "approved", "not allowed"
        )


def test_m2_durable_records_are_immutable_at_the_sqlite_boundary(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    run = store.create_run("daily", 1)
    artifact = store.write_artifact(run["id"], "candidate_text", b"candidate")
    trace = store.append_trace_event(
        run["id"],
        "step_intent",
        {"step_id": "generate-1", "kind": "generate", "state": "dispatched"},
    )
    commit_set = store.freeze_commit_set("M2", 1, {"sha": "abc"})
    review = store.record_milestone_review("M2", commit_set["id"], "passed", [])
    human = store.submit_human_review(
        "commit_set", commit_set["id"], "approved", "exact revision"
    )

    mutations = [
        ("UPDATE artifact SET sha256 = 'tampered' WHERE id = ?", (artifact["id"],)),
        (
            "DELETE FROM trace_event WHERE run_id = ? AND sequence = ?",
            (run["id"], trace["sequence"]),
        ),
        ("UPDATE commit_set SET payload_hash = 'tampered' WHERE id = ?", (commit_set["id"],)),
        ("DELETE FROM milestone_review WHERE id = ?", (review["id"],)),
        ("UPDATE human_review SET status = 'rejected' WHERE id = ?", (human["id"],)),
    ]
    for statement, parameters in mutations:
        with store.connect() as db, pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(statement, parameters)

    with store.connect() as db, pytest.raises(sqlite3.IntegrityError, match="duplicate"):
        db.execute(
            "INSERT OR REPLACE INTO commit_set VALUES (?, 'M2', 1, '{}', 'tampered', "
            "CURRENT_TIMESTAMP, 'pending')",
            (commit_set["id"],),
        )
