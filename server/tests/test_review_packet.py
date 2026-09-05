from __future__ import annotations

import hashlib

import pytest

from writing_ops.review_packet import build_review_packet


def test_review_packet_binds_every_review_input() -> None:
    packet = build_review_packet(
        goal_hierarchy={"daily": {"chapter": "ch001"}},
        chapter_contract={"must_happen": ["arrival"]},
        candidate_text="完整候选稿",
        writing_mcp_context={"facts": ["canon"]},
        previous_findings=[{"id": "P2-1"}],
        revision_relationships=[{"from": "draft-1", "to": "draft-2"}],
        skill_lock={"commit": "a7917c8b4951f540bb4da39b5f10b99dbacc45c0"},
        prompt_version="review-v1",
    )

    assert packet["candidate_text"] == "完整候选稿"
    assert packet["human_review_status"] == "pending"
    assert packet["hashes"]["candidate_text"] == hashlib.sha256(
        "完整候选稿".encode()
    ).hexdigest()
    assert set(packet["hashes"]) == {
        "goal_hierarchy",
        "chapter_contract",
        "candidate_text",
        "writing_mcp_context",
        "skill_lock",
        "prompt_version",
    }
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
