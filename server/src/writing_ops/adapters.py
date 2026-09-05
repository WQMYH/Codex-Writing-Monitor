from __future__ import annotations

import os
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


def acquire_edge_profile_lock(spec: EdgeLaunchSpec, *, owner_nonce: str) -> Path:
    spec.profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(spec.profile_lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as error:
        raise FileExistsError(f"Edge profile lock already exists: {spec.profile_lock}") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
        lock.write(owner_nonce)
    return spec.profile_lock


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
