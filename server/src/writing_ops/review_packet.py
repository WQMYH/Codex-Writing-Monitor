from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(value: object) -> str:
    if isinstance(value, str):
        encoded = value.encode()
    else:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_review_packet(
    *,
    goal_hierarchy: dict[str, Any],
    chapter_contract: dict[str, Any],
    candidate_text: str,
    writing_mcp_context: dict[str, Any],
    previous_findings: list[dict[str, Any]],
    revision_relationships: list[dict[str, Any]],
    skill_lock: dict[str, Any],
    prompt_version: str,
) -> dict[str, Any]:
    if not candidate_text:
        raise ValueError("candidate text is required")
    return {
        "goal_hierarchy": goal_hierarchy,
        "chapter_contract": chapter_contract,
        "candidate_text": candidate_text,
        "writing_mcp_context": writing_mcp_context,
        "previous_findings": previous_findings,
        "revision_relationships": revision_relationships,
        "skill_lock": skill_lock,
        "prompt_version": prompt_version,
        "hashes": {
            "goal_hierarchy": _digest(goal_hierarchy),
            "chapter_contract": _digest(chapter_contract),
            "candidate_text": _digest(candidate_text),
            "writing_mcp_context": _digest(writing_mcp_context),
            "previous_findings": _digest(previous_findings),
            "revision_relationships": _digest(revision_relationships),
            "skill_lock": _digest(skill_lock),
            "prompt_version": _digest(prompt_version),
        },
        "human_review_status": "pending",
    }
