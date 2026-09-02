from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / ".agents" / "skills" / "writing-ops-plan" / "SKILL.md"


def _content() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_execution_protocol_binds_one_status_source_and_source_identity() -> None:
    content = _content()

    assert content.count("**Status (single source of truth)**") == 1
    assert "docs/IMPLEMENTATION_STATUS.md" in content
    assert "sourcePlanRevision:" in content
    assert "sourcePlanDigest:" in content
    assert "skillflowManifestDigest:" in content


def test_execution_protocol_contains_every_required_runtime_section() -> None:
    content = _content()
    required_sections = (
        "## Document map",
        "## Recovery protocol",
        "## State determination protocol",
        "## Precise routing protocol",
        "## Task code anchors",
        "## Fix discipline",
        "## Commit rules",
        "## Known boundaries",
    )

    assert tuple(re.findall(r"^## .+$", content, flags=re.MULTILINE)) == required_sections


def test_execution_protocol_routes_unknown_effects_and_review_ceiling_safely() -> None:
    content = _content().lower()

    assert "unknown side-effect" in content
    assert "never replay" in content
    assert "review-budget exhaustion" in content
    assert "human adjudication" in content
    assert "cannot reset" in content


def test_execution_protocol_keeps_project_authority_and_skillflow_permissions_bounded() -> None:
    content = _content()

    assert "Storyforge > Writing MCP > PlotRail > candidate text" in content
    assert "cannot mutate SkillFlow's catalog" in content
    assert "cannot grant permissions" in content


def test_execution_protocol_has_no_copied_current_state() -> None:
    content = _content()

    assert "revision 6" not in content
    assert "M1-APPROVAL" not in content
    assert "22 Python tests" not in content
