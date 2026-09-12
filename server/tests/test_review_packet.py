from __future__ import annotations

import hashlib

import pytest

from writing_ops.review_packet import build_review_packet, gate_receipt_from_review
from writing_ops.service import WritingOpsService
from writing_ops.state import StateStore


def test_review_packet_binds_every_review_input() -> None:
    goal_hierarchy = {"daily": {"chapter": "ch001"}}
    chapter_contract = {"must_happen": ["arrival"]}
    writing_mcp_context = {"facts": ["canon"]}
    previous_findings = [{"id": "P2-1"}]
    revision_relationships = [{"from": "draft-1", "to": "draft-2"}]
    skill_lock = {"commit": "a7917c8b4951f540bb4da39b5f10b99dbacc45c0"}
    packet = build_review_packet(
        goal_hierarchy=goal_hierarchy,
        chapter_contract=chapter_contract,
        candidate_text="完整候选稿",
        writing_mcp_context=writing_mcp_context,
        previous_findings=previous_findings,
        revision_relationships=revision_relationships,
        skill_lock=skill_lock,
        prompt_version="review-v1",
    )

    assert packet["candidate_text"] == "完整候选稿"
    assert packet["human_review_status"] == "pending"
    assert packet["hashes"]["candidate_text"] == hashlib.sha256(
        "完整候选稿".encode()
    ).hexdigest()
    assert packet["hashes"]["previous_findings"] == hashlib.sha256(
        b'[{"id":"P2-1"}]'
    ).hexdigest()
    assert packet["hashes"]["revision_relationships"] == hashlib.sha256(
        b'[{"from":"draft-1","to":"draft-2"}]'
    ).hexdigest()
    assert set(packet["hashes"]) == {
        "goal_hierarchy",
        "chapter_contract",
        "candidate_text",
        "writing_mcp_context",
        "previous_findings",
        "revision_relationships",
        "skill_lock",
        "prompt_version",
    }
    previous_findings[0]["id"] = "tampered"
    revision_relationships[0]["to"] = "tampered"
    assert packet["previous_findings"] == [{"id": "P2-1"}]
    assert packet["revision_relationships"] == [{"from": "draft-1", "to": "draft-2"}]
    with pytest.raises(ValueError, match="candidate text"):
        build_review_packet(
            goal_hierarchy={},
            chapter_contract={},
            candidate_text="",
            writing_mcp_context={},
            previous_findings=[],
            revision_relationships=[],
            skill_lock={},
            prompt_version="review-v1",
        )


def test_gate_receipt_binds_the_verified_packet_and_system_gate() -> None:
    packet = build_review_packet(
        goal_hierarchy={"daily": {"chapter": "ch001"}},
        chapter_contract={"must_happen": ["arrival"]},
        candidate_text="完整候选稿",
        writing_mcp_context={"facts": ["canon"]},
        previous_findings=[],
        revision_relationships=[],
        skill_lock={"commit": "a7917c8b4951f540bb4da39b5f10b99dbacc45c0"},
        prompt_version="review-v1",
    )
    receipt = gate_receipt_from_review(
        packet=packet,
        verdict={"semantic_dimensions": {"continuity": "pass"}, "findings": []},
        deterministic_checks={"chapter_contract": True},
        required_dimensions=["continuity"],
        configured_model="configured-codex-model",
        task_id="codex-task-1",
        revision_count=0,
    )

    assert receipt["gate_status"] == "passed"
    packet["candidate_text"] = "tampered"
    with pytest.raises(ValueError, match="ReviewPacket hash verification failed"):
        gate_receipt_from_review(
            packet=packet,
            verdict={"semantic_dimensions": {"continuity": "pass"}, "findings": []},
            deterministic_checks={"chapter_contract": True},
            required_dimensions=["continuity"],
            configured_model="configured-codex-model",
            task_id="codex-task-1",
            revision_count=0,
        )


def test_service_persists_only_a_verified_review_verdict(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    service = WritingOpsService(store=store)
    run = store.create_run("daily", 1)
    packet = build_review_packet(
        goal_hierarchy={"daily": {"chapter": "ch001"}},
        chapter_contract={"must_happen": ["arrival"]},
        candidate_text="完整候选稿",
        writing_mcp_context={"facts": ["canon"]},
        previous_findings=[],
        revision_relationships=[],
        skill_lock={"commit": "a7917c8b4951f540bb4da39b5f10b99dbacc45c0"},
        prompt_version="review-v1",
    )

    receipt = service.record_review_verdict(
        run_id=run["id"],
        packet=packet,
        verdict={"semantic_dimensions": {"continuity": "pass"}, "findings": []},
        deterministic_checks={"chapter_contract": True},
        required_dimensions=["continuity"],
        configured_model="configured-codex-model",
        task_id="codex-task-1",
        revision_count=0,
    )

    assert receipt["payload"]["gate_status"] == "passed"
    assert store.list_gate_receipts() == [{**receipt, "integrity_status": "verified"}]
