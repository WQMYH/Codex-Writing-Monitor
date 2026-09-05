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
    ".pytest-tmp",
    ".test-tmp",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
BUNDLE_MANIFEST = "bundle-manifest.json"


def _ignored(path: str, names: list[str]) -> set[str]:
    current = Path(path)
    excluded = {name for name in names if name in EXCLUDED_NAMES}
    if current.name == "writing-ops":
        excluded.update(name for name in names if name in EXCLUDED_TOP_LEVEL)
    return excluded


def _file_manifest(root: Path) -> list[dict[str, str | int]]:
    entries: list[dict[str, str | int]] = []
    files = (
        item
        for item in root.rglob("*")
        if item.is_file()
        and item.name != BUNDLE_MANIFEST
        and not any(part in EXCLUDED_NAMES for part in item.relative_to(root).parts)
    )
    for path in sorted(files):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": relative, "sha256": digest, "size": path.stat().st_size})
    return entries


def seal_bundle(bundle_root: Path, source_root: Path | None = None) -> Path:
    bundle_root = bundle_root.resolve(strict=True)
    manifest_path = bundle_root / BUNDLE_MANIFEST
    manifest = {
        "schemaVersion": 1,
        "humanReviewStatus": "pending",
        "sourceRoot": str((source_root or bundle_root).resolve()),
        "files": _file_manifest(bundle_root),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def verify_bundle(bundle_root: Path) -> dict[str, object]:
    bundle_root = bundle_root.resolve(strict=True)
    manifest = json.loads((bundle_root / BUNDLE_MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("files") != _file_manifest(bundle_root):
        raise ValueError("bundle manifest does not match the installed artifact")
    if manifest.get("humanReviewStatus") != "pending":
        raise ValueError("bundle human review status must remain pending")
    return manifest


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
    seal_bundle(staging, source_root=plugin_root)

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
