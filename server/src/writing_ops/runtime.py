from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from writing_ops.loopback import validate_storyforge_origin

STORYFORGE_DEV_ENTRY = "node scripts/dev-with-writing-bridge.mjs"


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    storyforge_root: Path
    storyforge_origin: str
    storyforge_command: tuple[str, str] = ("npm.cmd", "run", "dev")


def load_runtime_configuration(path: Path) -> RuntimeConfiguration:
    configuration = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configuration, dict) or set(configuration) != {
        "storyforgeRoot",
        "storyforgeOrigin",
    }:
        raise ValueError("runtime configuration has invalid keys")
    root = Path(configuration["storyforgeRoot"]).resolve(strict=True)
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    if (
        package.get("name") != "storyforge"
        or package.get("scripts", {}).get("dev") != STORYFORGE_DEV_ENTRY
    ):
        raise ValueError("Storyforge dev entry is not verified")
    return RuntimeConfiguration(
        storyforge_root=root,
        storyforge_origin=validate_storyforge_origin(configuration["storyforgeOrigin"]),
    )
