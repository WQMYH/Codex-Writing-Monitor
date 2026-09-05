from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class EdgeLaunchSpec:
    edge_executable: Path
    profile_dir: Path
    profile_lock: Path
    storyforge_origin: str
    command: tuple[str, ...]


def build_edge_launch_spec(
    *, edge_executable: Path, runtime_root: Path, storyforge_origin: str
) -> EdgeLaunchSpec:
    from writing_ops.loopback import validate_storyforge_origin

    edge = edge_executable.resolve(strict=True)
    if not edge.is_file() or edge.name.lower() != "msedge.exe":
        raise ValueError("Edge executable must be an existing msedge.exe file")
    root = runtime_root.resolve()
    profile_dir = root / "edge-profile"
    return EdgeLaunchSpec(
        edge_executable=edge,
        profile_dir=profile_dir,
        profile_lock=root / "edge-profile.lock",
        storyforge_origin=validate_storyforge_origin(storyforge_origin),
        command=(
            str(edge),
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ),
    )


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
