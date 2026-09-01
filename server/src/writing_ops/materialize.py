from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

EXCLUDED_TOP_LEVEL = {".dist", ".git", ".skillflow"}
EXCLUDED_NAMES = {
    ".pytest_cache",
    ".test-tmp",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}


def _ignored(path: str, names: list[str]) -> set[str]:
    current = Path(path)
    excluded = {name for name in names if name in EXCLUDED_NAMES}
    if current.name == "writing-ops":
        excluded.update(name for name in names if name in EXCLUDED_TOP_LEVEL)
    return excluded


def _file_manifest(root: Path) -> list[dict[str, str | int]]:
    entries: list[dict[str, str | int]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": relative, "sha256": digest, "size": path.stat().st_size})
    return entries


def _replace_with_retry(source: Path, target: Path) -> None:
    for attempt in range(6):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def materialize(plugin_root: Path) -> Path:
    plugin_root = plugin_root.resolve(strict=True)
    if plugin_root.name != "writing-ops":
        raise ValueError(f"unexpected plugin root: {plugin_root}")

    dist_root = plugin_root / ".dist"
    dist_root.mkdir(exist_ok=True)
    staging = dist_root / f"staging-{uuid.uuid4().hex}"
    current = dist_root / "current"
    previous = dist_root / "previous"

    shutil.copytree(plugin_root, staging, ignore=_ignored)
    manifest = {
        "schemaVersion": 1,
        "humanReviewStatus": "pending",
        "sourceRoot": str(plugin_root),
        "files": _file_manifest(staging),
    }
    (staging / "bundle-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if previous.exists():
        shutil.rmtree(previous)
    if current.exists():
        _replace_with_retry(current, previous)
    try:
        _replace_with_retry(staging, current)
    except PermissionError:
        if previous.exists() and not current.exists():
            _replace_with_retry(previous, current)
        raise
    if previous.exists():
        shutil.rmtree(previous)
    return current
