from __future__ import annotations

import json
import sqlite3

import pytest

from writing_ops.service import WritingOpsService
from writing_ops.state import DAILY_REQUIRED, StateStore, payload_hash

SHA_A = "a" * 40
SHA_B = "b" * 40
HASH_A = "a" * 64
HASH_B = "b" * 64


def commit_set_payload(revision: int = 1) -> dict[str, object]:
    return {
        "schema_version": 1,
        "milestone_id": "M2",
        "revision": revision,
        "repositories": {
            "writing_ops": {"base": SHA_A, "head": SHA_B},
            "storyforge": {"base": SHA_A, "head": SHA_B},
            "writing_mcp": {"baseline": SHA_A, "modified": False},
        },
        "installed_plugin": {
            "version": "0.1.0+codex.test",
            "build_id": f"sha256:{HASH_A}",
            "marketplace": "gameops-local",
            "sealed_smoke": "passed",
        },
        "review_package": {"sha256": HASH_B, "size": 1024},
        "machine_gate": {"receipt_hash": HASH_A, "status": "passed"},
        "human_review_status": "pending",
    }


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


def gate_receipt_payload(run_id: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "review_packet_hash": HASH_A,
        "candidate_hash": HASH_A,
        "context_hash": HASH_B,
        "configured_model": "configured-codex-model",
        "task_id": "codex-task-1",
        "prompt_version": "review-v1",
        "input_hash": HASH_A,
        "output_hash": HASH_B,
        "deterministic_checks": {"chapter_contract": True},
        "required_dimensions": ["continuity"],
        "semantic_dimensions": {"continuity": "pass"},
        "findings": [],
        "revision_count": 0,
        "gate_status": "passed",
        "human_review_status": "pending",
    }


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


def test_secret_material_is_rejected_before_artifact_or_trace_persistence(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    run = store.create_run("daily", 1)

    with pytest.raises(ValueError, match="secret material"):
        store.write_artifact(
            run["id"],
            "candidate_text",
            b"Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        )
    assert not list((tmp_path / "artifacts").rglob("*"))
    assert store.list_artifacts() == []

    with pytest.raises(ValueError, match="secret material"):
        store.append_trace_event(
            run["id"],
            "runtime_status",
            {
                "component": "edge",
                "state": "blocked",
                "pid": 10,
                "port": 9222,
                "detail": "Cookie: session=abcdefghijklmnopqrstuvwxyz012345",
            },
        )
    with pytest.raises(ValueError, match="secret material"):
        store.append_trace_event(
            run["id"],
            "browser_action",
            {
                "action": "read",
                "origin": "http://127.0.0.1:5173",
                "result": "access_token=abcdefghijklmnopqrstuvwxyz012345",
                "error_code": None,
            },
        )
    with pytest.raises(ValueError, match="secret material"):
        store.append_trace_event(
            run["id"],
            "runtime_status",
            {
                "component": "storyforge",
                "state": "blocked",
                "pid": None,
                "port": 43125,
                "detail": (
                    "#session=abcdefghijklmnopqrstuvwxyz123456"
                    "&csrf=zyxwvutsrqponmlkjihgfedcba654321"
                ),
            },
        )
    with pytest.raises(ValueError, match="valid integer"):
        store.append_trace_event(
            run["id"],
            "runtime_status",
            {
                "component": "edge",
                "state": "blocked",
                "pid": "10",
                "port": 9222,
                "detail": "safe",
            },
        )
    assert store.list_trace_events() == []


def test_m5_persists_safe_artifact_and_trace(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    run = store.create_run("daily", 1)

    artifact = store.write_artifact(run["id"], "candidate_text", b"safe candidate text")
    event = store.append_trace_event(
        run["id"],
        "step_intent",
        {"step_id": "generate-1", "kind": "generate", "state": "dispatched"},
    )
    acknowledgement = store.append_trace_event(
        run["id"],
        "step_ack",
        {"step_id": "generate-1", "outcome": "accepted", "state": "acknowledged"},
    )

    assert artifact["human_review_status"] == "pending"
    assert store.list_artifacts() == [{**artifact, "integrity_status": "verified"}]
    assert event["sequence"] == 1
    assert acknowledgement["sequence"] == 2
    assert acknowledgement["previous_hash"] == event["event_hash"]
    assert store.list_trace_events() == [
        {**event, "integrity_status": "verified"},
        {**acknowledgement, "integrity_status": "verified"},
    ]


def test_m5_records_only_evidence_backed_gate_receipts(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    run = store.create_run("daily", 1)
    receipt = store.record_gate_receipt(run["id"], gate_receipt_payload(run["id"]))

    assert receipt["human_review_status"] == "pending"
    assert receipt["payload"]["gate_status"] == "passed"
    assert store.list_gate_receipts() == [{**receipt, "integrity_status": "verified"}]
    assert WritingOpsService(store=store).dashboard().reviewer.gate_receipts[0].id == receipt["id"]

    blocked = gate_receipt_payload(run["id"])
    blocked["semantic_dimensions"] = {"continuity": "uncertain"}
    blocked["gate_status"] = "blocked"
    assert store.record_gate_receipt(run["id"], blocked)["payload"]["gate_status"] == "blocked"

    invalid = gate_receipt_payload(run["id"])
    invalid["semantic_dimensions"] = {"continuity": "uncertain"}
    with pytest.raises(ValueError, match="GateReceipt payload is invalid"):
        store.record_gate_receipt(run["id"], invalid)

    other_run = store.create_run("other-daily", 1)
    with pytest.raises(ValueError, match="GateReceipt run binding mismatch"):
        store.record_gate_receipt(other_run["id"], gate_receipt_payload(run["id"]))


def test_m5_rejects_legacy_gate_receipts_without_run_binding(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    run = store.create_run("daily", 1)
    legacy = gate_receipt_payload(run["id"])
    legacy.pop("run_id")
    with store.connect() as db:
        db.execute(
            "INSERT INTO gate_receipt VALUES (?, ?, ?, ?, ?, 'pending')",
            ("legacy", run["id"], json.dumps(legacy), payload_hash(legacy), "2026-09-12"),
        )

    with pytest.raises(ValueError, match="run binding"):
        store.list_gate_receipts()


@pytest.mark.parametrize(
    "finding",
    [
        {"severity": "P0", "dimension": None},
        {"severity": "P1", "dimension": None},
        {"severity": "P2", "dimension": "continuity"},
    ],
)
def test_m5_rejects_passed_receipts_with_blocking_findings(tmp_path, finding) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    run = store.create_run("daily", 1)
    payload = gate_receipt_payload(run["id"])
    payload["findings"] = [finding]

    with pytest.raises(ValueError, match="GateReceipt payload is invalid"):
        store.record_gate_receipt(run["id"], payload)


@pytest.mark.parametrize(
    "secret",
    [
        b"-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEIGZha2U=\n-----END PRIVATE KEY-----",
        b"ghp_abcdefghijklmnopqrstuvwxyz0123456789AB",
        b"sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
        b"AKIAIOSFODNN7EXAMPLE",
    ],
)
def test_unlabelled_secret_signatures_never_reach_artifact_storage(
    tmp_path, secret: bytes
) -> None:
    store = StateStore(tmp_path / "state.sqlite3")

    with pytest.raises(ValueError, match="secret material"):
        store.write_artifact(None, "candidate_text", b"candidate\n" + secret)

    assert not list((tmp_path / "artifacts").rglob("*"))
    assert store.list_artifacts() == []


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (
            "browser_action",
            {
                "action": "read",
                "origin": "http://user:password@127.0.0.1:5173",
                "result": "ok",
                "error_code": None,
            },
        ),
        (
            "browser_action",
            {
                "action": "read",
                "origin": "http://127.0.0.1:5173",
                "result": "-----BEGIN PRIVATE KEY-----",
                "error_code": None,
            },
        ),
        (
            "runtime_status",
            {
                "component": "storyforge",
                "state": "blocked",
                "pid": None,
                "port": 43125,
                "detail": "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB",
            },
        ),
    ],
)
def test_trace_semantic_fields_reject_credentials_and_free_form_secrets(
    tmp_path, event_type: str, payload: dict[str, object]
) -> None:
    store = StateStore(tmp_path / "state.sqlite3")

    with pytest.raises(ValueError, match="trace payload|secret material"):
        store.append_trace_event("run-secret", event_type, payload)

    assert store.list_trace_events() == []


def test_commit_set_and_review_state_are_projected_and_human_decisions_are_explicit(
    tmp_path,
) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    commit_set = store.freeze_commit_set("M2", 1, commit_set_payload())
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
    assert view_model.reviewer.commit_sets[0].integrity_status == "verified"
    assert view_model.reviewer.milestone_reviews[0].id == milestone_review["id"]
    assert view_model.reviewer.milestone_reviews[0].human_review_status == "pending"
    assert view_model.reviewer.human_reviews[0].comment == "accept this exact revision"
    assert commit_set["id"] in view_model.text_dashboard
    assert "passed_with_findings" in view_model.text_dashboard
    assert view_model.milestone_state == "completed"
    assert view_model.independent_review_status == "passed"
    assert view_model.human_review_status == "approved"
    assert view_model.reviewer.human_review_status == "approved"
    with pytest.raises(ValueError, match="subject type"):
        WritingOpsService(store=store).human_review_submit(
            "sqlite_master", "anything", "approved", "not allowed"
        )


def test_commit_set_schema_rejects_partial_extra_and_mismatched_candidates(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    with pytest.raises(ValueError, match="CommitSet"):
        store.freeze_commit_set("M2", 1, {"sha": "abc"})

    extra = commit_set_payload()
    extra["unexpected"] = True
    with pytest.raises(ValueError, match="CommitSet"):
        store.freeze_commit_set("M2", 1, extra)

    mismatched = commit_set_payload(revision=2)
    with pytest.raises(ValueError, match="identity"):
        store.freeze_commit_set("M2", 1, mismatched)

    with store.connect() as db:
        db.execute(
            "INSERT INTO commit_set VALUES (?, 'M2', 9, ?, ?, CURRENT_TIMESTAMP, 'pending')",
            (
                "raw-invalid-v1",
                json.dumps({"schema_version": 1}),
                payload_hash({"schema_version": 1}),
            ),
        )
    with pytest.raises(ValueError, match="CommitSet integrity"):
        store.list_commit_sets()


def test_milestone_review_findings_require_a_list_and_project_legacy_damage(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    commit_set = store.freeze_commit_set("M2", 1, commit_set_payload())

    with pytest.raises(ValueError, match="findings"):
        store.record_milestone_review("M2", commit_set["id"], "failed", {"id": "wrong-shape"})

    with store.connect() as db:
        db.execute(
            "INSERT INTO milestone_review VALUES "
            "(?, 'M2', ?, 'failed', ?, CURRENT_TIMESTAMP, 'pending')",
            ("malformed-review", commit_set["id"], json.dumps({"id": "wrong-shape"})),
        )

    snapshot = WritingOpsService(store=store).dashboard()
    review = snapshot.reviewer.milestone_reviews[0]
    assert review.findings == [
        {"id": "milestone_review_findings_invalid", "disposition": "block_now"}
    ]


def test_rejected_commit_set_is_projected_without_mutating_the_frozen_subject(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    commit_set = store.freeze_commit_set("M2", 1, commit_set_payload())
    store.submit_human_review("commit_set", commit_set["id"], "rejected", "needs repair")

    snapshot = WritingOpsService(store=store).dashboard()
    assert snapshot.milestone_state == "review_ready"
    assert snapshot.independent_review_status == "pending"
    assert snapshot.human_review_status == "rejected"
    assert snapshot.reviewer.human_review_status == "rejected"
    assert snapshot.reviewer.commit_sets[0].human_review_status == "rejected"


def test_human_rejection_blocks_progress_even_after_independent_review_passed(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    commit_set = store.freeze_commit_set("M2", 1, commit_set_payload())
    store.record_milestone_review("M2", commit_set["id"], "passed", [])
    store.submit_human_review("commit_set", commit_set["id"], "rejected", "needs repair")

    snapshot = WritingOpsService(store=store).dashboard()

    assert snapshot.milestone_state == "implementing"
    assert snapshot.independent_review_status == "passed"
    assert snapshot.human_review_status == "rejected"
    assert snapshot.blocked == ["human_review_rejected"]
    assert "M3" not in snapshot.next_action


def test_m2_durable_records_are_immutable_at_the_sqlite_boundary(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    commit_set = store.freeze_commit_set("M2", 1, commit_set_payload())
    review = store.record_milestone_review("M2", commit_set["id"], "passed", [])
    human = store.submit_human_review(
        "commit_set", commit_set["id"], "approved", "exact revision"
    )

    mutations = [
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
