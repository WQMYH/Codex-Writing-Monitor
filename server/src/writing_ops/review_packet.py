from __future__ import annotations

import hashlib
import json
from typing import Any

from writing_ops.models import ReviewVerdict, gate_status_for_evidence


def _digest(value: object) -> str:
    if isinstance(value, str):
        encoded = value.encode()
    else:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _frozen_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def review_packet_hash(packet: dict[str, Any]) -> str:
    return _digest(packet)


def gate_receipt_from_review(
    *,
    packet: dict[str, Any],
    verdict: dict[str, Any],
    deterministic_checks: dict[str, bool],
    required_dimensions: list[str],
    configured_model: str,
    task_id: str,
    revision_count: int,
) -> dict[str, Any]:
    packet_fields = {
        "goal_hierarchy",
        "chapter_contract",
        "candidate_text",
        "writing_mcp_context",
        "previous_findings",
        "revision_relationships",
        "skill_lock",
        "prompt_version",
    }
    hashes = packet.get("hashes")
    if not isinstance(hashes, dict) or set(hashes) != packet_fields:
        raise ValueError("ReviewPacket hashes are incomplete")
    if any(hashes[key] != _digest(packet.get(key)) for key in packet_fields):
        raise ValueError("ReviewPacket hash verification failed")
    parsed = ReviewVerdict.model_validate(verdict)
    packet_digest = review_packet_hash(packet)
    return {
        "schema_version": 1,
        "review_packet_hash": packet_digest,
        "candidate_hash": hashes["candidate_text"],
        "context_hash": hashes["writing_mcp_context"],
        "configured_model": configured_model,
        "task_id": task_id,
        "prompt_version": packet["prompt_version"],
        "input_hash": packet_digest,
        "output_hash": _digest(parsed.model_dump(mode="json")),
        "deterministic_checks": deterministic_checks,
        "required_dimensions": required_dimensions,
        "semantic_dimensions": parsed.semantic_dimensions,
        "findings": [finding.model_dump(mode="json") for finding in parsed.findings],
        "revision_count": revision_count,
        "gate_status": gate_status_for_evidence(
            deterministic_checks, required_dimensions, parsed
        ),
        "human_review_status": "pending",
    }


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
    goal_hierarchy = _frozen_json(goal_hierarchy)
    chapter_contract = _frozen_json(chapter_contract)
    writing_mcp_context = _frozen_json(writing_mcp_context)
    previous_findings = _frozen_json(previous_findings)
    revision_relationships = _frozen_json(revision_relationships)
    skill_lock = _frozen_json(skill_lock)
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
