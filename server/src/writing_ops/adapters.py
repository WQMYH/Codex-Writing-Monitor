from __future__ import annotations

from typing import Any, Protocol


class WritingHostAdapter(Protocol):
    def runtime_status(self) -> dict[str, Any]: ...


class FakeWritingHostAdapter:
    def runtime_status(self) -> dict[str, Any]:
        return {
            "adapter": "fake",
            "storyforge": "not_started",
            "writing_mcp": "not_started",
            "edge": "not_started",
            "browser_worker": "not_started",
            "human_review_status": "pending",
        }
